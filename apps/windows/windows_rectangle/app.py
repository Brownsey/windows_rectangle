"""Composition root — the only place adapters get bound to ports.

`AppContext` wires Settings into a Dispatcher + CleanupRegistry. The
win32 adapters import lazily inside `bind_win32()` so that pytest on
non-Windows CI doesn't pay for native/Qt imports just to test
core. The dispatcher itself is fully driveable via any `WindowManager`
fake, as the tests demonstrate.
"""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from .core.actionbus import ActionBus
from .core.actions import Action
from .core.cleanup import CleanupRegistry
from .core.cycle import CycleState
from .core.dispatcher import Dispatcher
from .core.dragsession import DragSession
from .core.eligibility import Capability, classify
from .core.geometry import Rect
from .core.history import History
from .core.snap import SnapHit
from .core.workspace_service import (
    WorkspaceResult,
    WorkspaceWindows,
    apply_workspace,
    capture_workspace,
)
from .ports.config_store import ConfigStore, Settings

if TYPE_CHECKING:
    from .ports.autostart import AutoStart
    from .ports.hotkeys import Hotkeys
    from .ports.single_instance import SingleInstance
    from .ports.window_manager import WindowManager


class SecondInstanceError(RuntimeError):
    """Raised by `build()` when the SingleInstance guard is already held.

    Main entrypoint should catch this, surface the existing tray icon,
    and exit cleanly (brief §6).
    """


_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BindingReport:
    """Outcome of the last hotkey registration pass.

    Lets the tray surface "X of Y bound" without having to introspect
    the OS-level Hotkeys adapter. The error message stored in `failed`
    is the `str(exc)` of whatever the register call raised — it's a
    human-readable hint, not anything semantically structured.
    """

    bound: tuple[tuple[Action, str], ...] = ()
    failed: tuple[tuple[Action, str, str], ...] = ()
    workspace_bound: tuple[tuple[str, str, str], ...] = ()
    workspace_failed: tuple[tuple[str, str, str, str], ...] = ()
    # User paused the global hotkey set (via the tray "Pause shortcuts"
    # toggle). When True, `bound` still describes what *would* be
    # registered on resume — we don't squash it into `failed` because
    # paused != failed semantically.
    paused: bool = False

    @property
    def total(self) -> int:
        return (
            len(self.bound)
            + len(self.failed)
            + len(self.workspace_bound)
            + len(self.workspace_failed)
        )

    @property
    def bound_count(self) -> int:
        # When paused the hotkeys aren't actually live, so the count of
        # *currently registered* combos is zero. `len(self.bound)` is
        # still available via `would_bind_count`.
        if self.paused:
            return 0
        return len(self.bound) + len(self.workspace_bound)

    @property
    def would_bind_count(self) -> int:
        """How many combos `bound` lists, ignoring paused-ness.

        Lets the tray say "0/22 bound (paused)" rather than collapsing
        the count to zero with no context.
        """
        return len(self.bound) + len(self.workspace_bound)

    @property
    def failed_count(self) -> int:
        return len(self.failed) + len(self.workspace_failed)

    @property
    def all_bound(self) -> bool:
        return (
            not self.failed
            and not self.workspace_failed
            and bool(self.bound or self.workspace_bound)
            and not self.paused
        )


# Sentinel "no binding has happened yet" — clearer than None at the call
# sites that want to display a status line on a fresh AppContext.
EMPTY_BINDING_REPORT = BindingReport()


@dataclass(slots=True)
class AppContext:
    """One-stop handle on every wired component.

    Build it via `build(...)` from tests with a fake `WindowManager`, or
    via `bind_win32(...)` at runtime for a real Windows shell.
    """

    settings: Settings
    windows: WindowManager
    dispatcher: Dispatcher
    drag: DragSession
    cleanup: CleanupRegistry = field(default_factory=CleanupRegistry)
    hotkeys: Hotkeys | None = None
    config_store: ConfigStore | None = None
    autostart: AutoStart | None = None
    autostart_command_line: str | None = None
    single_instance: SingleInstance | None = None
    bus: ActionBus = field(default_factory=ActionBus)
    # True iff the on-disk config file didn't exist at startup — the tray
    # uses this to surface a one-shot welcome balloon explaining where
    # to find Preferences. Set by bind_win32; tests/build() can flip it
    # explicitly when they want to assert the same UX path.
    first_run: bool = False
    # Outcome of the last hotkey binding pass. `_bind_shortcuts` writes
    # here as a side effect so the tray can render a "X of Y bound"
    # tooltip and a "Binding status…" dialog listing failures without
    # peeking at the win32 hotkeys adapter directly. Starts as the
    # empty report so a fresh AppContext (no binding has fired yet)
    # still has something to format.
    last_binding_report: BindingReport = field(default_factory=lambda: EMPTY_BINDING_REPORT)
    # Last rect handed to the overlay's on_show, or None when hidden. Used
    # by drain_drag_preview to dedup callbacks at 60 Hz (most ticks are
    # idle — calling Qt's hide() on an already-hidden widget burns time).
    _preview_state: Rect | None = field(default=None, init=False, repr=False)
    # Monotonic wall-clock of the last cycle/history prune. Initialised
    # to -inf so the very first maintenance() call always runs. The
    # QTimer invokes maintenance() on every tick but prune work only
    # runs at most once per `prune_interval` seconds — sweeping every
    # 16ms would call IsWindow() across the whole history dict each tick.
    _last_prune: float = field(default=float("-inf"), init=False, repr=False)
    prune_interval: float = 60.0
    # Subscribers invoked after apply_settings has fully wired the new
    # state. Used by the tray to refresh tooltip + "launch at login"
    # checkbox when the user changes prefs (and by anything else that
    # caches a derived view of Settings).
    _settings_subscribers: list[Callable[[Settings], None]] = field(
        default_factory=list, init=False, repr=False
    )
    # Live (hook, detector) pair when WH_MOUSE_LL is installed. Owned by
    # start_mousehook / stop_mousehook so the drag-to-edge toggle in
    # prefs can flip without restarting the app (lifts the documented
    # restriction noted on bind_mousehook).
    # Concrete element types are intentionally vague (`object`) because
    # the hook class is a lazy Win32 import — annotating the precise
    # type here would force the adapter import at module load.
    _mousehook: tuple[object, object] | None = field(default=None, init=False, repr=False)
    # One-shot guard for stop_mousehook cleanup registration. start_mousehook
    # is called once at startup and again on every False→True drag-to-edge
    # toggle; without this guard each install would push a duplicate
    # cleanup handler.
    _mousehook_cleanup_registered: bool = field(default=False, init=False, repr=False)
    # User-driven pause flag for the global hotkey set. When True we
    # unregister every combo but keep the Settings/Dispatcher state
    # intact so the next `resume_hotkeys()` re-registers without
    # touching `Settings.shortcuts`. Used by the tray "Pause shortcuts"
    # toggle so a user can free up the keymap during full-screen apps
    # without losing their bindings.
    paused: bool = field(default=False, init=False, repr=False)
    _workspace_queue: queue.Queue[str] = field(
        default_factory=lambda: queue.Queue(maxsize=64), init=False, repr=False
    )
    last_workspace_result: WorkspaceResult | None = field(default=None, init=False)
    _drag_handle: object | None = field(default=None, init=False, repr=False)
    _pending_snap: tuple[object, SnapHit] | None = field(default=None, init=False, repr=False)

    def apply_settings(self, settings: Settings) -> None:
        """Mutate the live dispatcher to reflect new user settings.

        Used by the prefs UI after `ConfigStore.save(...)`. If the user
        rebound any shortcuts, we re-register them with the hotkeys
        adapter so the new combos take effect without a restart (brief
        note: "all shortcuts can be configured... those shortcuts work").
        """
        shortcuts_changed = settings.shortcuts != self.settings.shortcuts
        workspace_shortcuts_changed = tuple(
            (workspace.id, workspace.shortcut) for workspace in settings.workspaces
        ) != tuple((workspace.id, workspace.shortcut) for workspace in self.settings.workspaces)
        drag_toggle_changed = settings.drag_to_edge_enabled != self.settings.drag_to_edge_enabled
        self.settings = settings
        self.dispatcher.gap = settings.gap
        # Cycle idle timeout is on the CycleState, not the Dispatcher.
        # The dispatcher uses whichever CycleState we gave it.
        self.dispatcher._cycle.idle_timeout = settings.cycle_idle_timeout
        self.dispatcher.almost_maximize_scale = settings.almost_maximize_scale
        self.drag.gap = settings.gap
        if (shortcuts_changed or workspace_shortcuts_changed) and self.hotkeys is not None:
            self.rebind_hotkeys()
        # Mirror the drag-to-edge toggle into the WH_MOUSE_LL lifecycle.
        # Lifts the restart restriction that bind_mousehook used to
        # document — enabling drag-to-edge now installs the hook on the
        # spot; disabling tears it down.
        if drag_toggle_changed:
            if settings.drag_to_edge_enabled:
                self.start_mousehook()
            else:
                self.stop_mousehook()
        self.sync_autostart()
        # Notify subscribers AFTER everything has been wired through, so
        # they observe a coherent state (and a subscriber's exception
        # can't leave us half-applied).
        for sub in self._settings_subscribers:
            try:
                sub(settings)
            except Exception:  # noqa: BLE001
                _log.exception("settings subscriber raised")

    def pause_hotkeys(self) -> bool:
        """Unregister every hotkey but keep Settings/bindings intact.

        Returns True iff the pause took effect (i.e. there was a hotkeys
        adapter to unregister against and we weren't already paused).
        Idempotent: a second call while paused is a no-op.

        Notify subscribers so the tray's "Pause shortcuts" checkbox
        stays in sync with the truth.
        """
        if self.hotkeys is None or self.paused:
            return False
        try:
            self.hotkeys.unregister_all()
        except Exception:  # noqa: BLE001
            _log.exception("pause_hotkeys: unregister_all raised")
            return False
        self.paused = True
        # Carry the previously-bound entries forward but set the
        # `paused` flag, so the Binding Status dialog can render them
        # distinctly (greyed-out "would re-register" rather than red
        # "failed"). Real failures stay in `failed` so the user can
        # still see them while paused.
        prev = self.last_binding_report
        self.last_binding_report = BindingReport(
            bound=prev.bound,
            failed=prev.failed,
            workspace_bound=prev.workspace_bound,
            workspace_failed=prev.workspace_failed,
            paused=True,
        )
        self._notify_settings_subscribers()
        return True

    def resume_hotkeys(self) -> bool:
        """Re-register every hotkey from the current Settings.

        Returns True iff we transitioned from paused → running. The
        re-registration goes through the ActionBus path so callbacks
        still don't run on the pump thread.
        """
        if self.hotkeys is None or not self.paused:
            return False
        self.paused = False
        bind_hotkeys_via_bus(self, self.hotkeys.register)
        self._notify_settings_subscribers()
        return True

    def _notify_settings_subscribers(self) -> None:
        """Push the current Settings to every subscriber. Used by the
        pause/resume helpers so the tray refreshes its tooltip + check
        states without us having to round-trip through apply_settings."""
        for sub in self._settings_subscribers:
            try:
                sub(self.settings)
            except Exception:  # noqa: BLE001
                _log.exception("settings subscriber raised")

    def reload_config(self) -> bool:
        """Re-read Settings from the ConfigStore and apply them.

        Useful when the user hand-edits `%APPDATA%\\windows_rectangle\\
        config.json` while the app is running. No-op (returns False) if
        no config_store is wired. Returns True on a successful load+
        apply; False on either a missing store or a load error (errors
        are logged — never raised at the caller, which is usually a
        tray click handler).
        """
        if self.config_store is None:
            return False
        try:
            new_settings = self.config_store.load()
        except Exception:  # noqa: BLE001 — surface as toast in UI, not crash
            _log.exception("reload_config: load failed")
            return False
        self.apply_settings(new_settings)
        return True

    def log_file_path(self) -> str | None:
        """Filesystem path of the rotating log file, or None if no
        store/log is configured yet.

        Used by the tray "Open log file…" item. Pure derivation from
        the on-disk default (`log_file.default_log_path`) — never
        returns a non-existent path you can't act on.
        """
        from .log_file import default_log_path

        try:
            return str(default_log_path())
        except Exception:  # noqa: BLE001 — never crash the tray click
            _log.debug("log_file_path lookup failed", exc_info=True)
            return None

    def config_folder(self) -> str | None:
        """Filesystem directory holding the config file, or None if no
        store is wired. Used by tray's "Open config folder…" so the
        user can hand-edit JSON / back up / share the file. Doesn't
        touch the disk — pure derivation from the store's path.
        """
        if self.config_store is None:
            return None
        # JsonConfigStore exposes `.path`; we don't import it here to
        # avoid an adapter dep — the duck-typed read keeps the AppContext
        # core/ports-only.
        path = getattr(self.config_store, "path", None)
        if path is None:
            return None
        try:
            return str(path.parent)
        except AttributeError:
            return None

    def subscribe_settings(self, callback: Callable[[Settings], None]) -> None:
        """Register a callback invoked after every apply_settings.

        The callback receives the new Settings and is expected to update
        any derived UI state (tray tooltip, prefs preview, etc.). Errors
        are caught and logged so a buggy subscriber can't poison the rest.
        """
        self._settings_subscribers.append(callback)

    def rebind_hotkeys(self) -> int:
        """Unregister every hotkey and re-register from `self.settings.shortcuts`.

        Returns the count of successful (re-)registrations. No-op if no
        hotkeys adapter is wired. Failures of individual combos are
        tolerated — the prefs UI surfaces them as warnings before commit,
        and an OS-clash here is logged but doesn't break the rebind.

        A failure inside `unregister_all` (rare; would normally only
        happen if the Win32 pump thread is in a bad state) is caught so
        we still attempt to register the new bindings — better to leave
        the OS with a half-rebound set than to skip rebinding entirely.
        """
        if self.hotkeys is None:
            return 0
        if self.paused:
            self.last_binding_report = BindingReport(
                bound=tuple(self.settings.shortcuts.items()),
                workspace_bound=tuple(
                    (workspace.id, workspace.name, workspace.shortcut)
                    for workspace in self.settings.workspaces
                    if workspace.shortcut.strip()
                ),
                paused=True,
            )
            return 0
        try:
            self.hotkeys.unregister_all()
        except Exception:  # noqa: BLE001
            _log.exception("hotkey unregister_all raised — continuing with rebind")
        return bind_hotkeys_via_bus(self, self.hotkeys.register)

    def sync_autostart(self) -> None:
        """Reconcile the AutoStart adapter with `settings.launch_at_login`.

        No-op if no autostart adapter or command line was wired. Failures
        are logged, not raised — a registry hiccup must not crash the app.
        """
        if self.autostart is None or self.autostart_command_line is None:
            return
        target = self.settings.launch_at_login
        try:
            currently = self.autostart.is_enabled()
            if target and not currently:
                self.autostart.enable(self.autostart_command_line)
            elif not target and currently:
                self.autostart.disable()
        except Exception:  # noqa: BLE001 — registry failure should never kill the app
            _log.exception("autostart sync failed")

    # ----- drag-to-edge facade (brief §2 #13) ------------------------

    def begin_drag(self, window: Rect) -> None:
        """Start a drag-snap session for `window`. Refreshes monitor list
        so a hotplug between drags is picked up.
        """
        if not self.settings.drag_to_edge_enabled:
            return
        self._drag_handle = self.windows.get_active_window()
        self.drag.monitors = self.windows.list_monitors()
        self.drag.gap = self.settings.gap
        self.drag.start(window)

    def begin_drag_for_active_window(self) -> bool:
        """Look up the foreground window and begin a drag session for it.

        Returns True iff a session was started — i.e. drag-to-edge is
        enabled, the foreground window exists, and it's eligible for
        movement. Designed for `DragDetector.on_begin`.
        """
        if not self.settings.drag_to_edge_enabled:
            return False
        handle = self.windows.get_active_window()
        if handle is None:
            return False
        try:
            rect = self.windows.get_window_rect(handle)
        except Exception:  # noqa: BLE001 — adapter raised, treat as no eligible window
            _log.debug("get_window_rect failed during drag begin", exc_info=True)
            return False
        self.begin_drag(rect)
        return self.drag.active

    def drag_update(self, x: int, y: int) -> None:
        """Mouse-hook hot-path callback. O(1)."""
        self.drag.update(x, y)

    def drag_poll(self) -> SnapHit | None:
        """UI timer callback (~60 Hz). Returns current preview or None."""
        return self.drag.poll()

    def end_drag(self) -> Action | None:
        """Mouse-up: dispatch the snap action if a zone is held, else None.

        Synchronous dispatch — use only when you're already on the main
        thread (e.g. in tests). The mouse-hook thread should call
        `end_drag_via_bus()` instead, otherwise the WH_MOUSE_LL hook
        proc blocks on Win32 syscalls (brief §5 #7).

        Returns the dispatched Action so callers can show feedback.
        """
        hit = self.drag.finish()
        if hit is None or hit.action is None:
            return None
        handle, self._drag_handle = self._drag_handle, None
        if handle is not None and hit.target is not None:
            self.dispatcher.dispatch_target(handle, hit.action, hit.target)
        return hit.action

    def end_drag_via_bus(self) -> Action | None:
        """Queue the final HWND and exact target for the next main-thread drain.

        Kept for callers that want deferred placement. Like the rest of the
        DragSession facade, call this on the main thread; the mouse hook uses
        the input mailbox instead.
        """
        hit = self.drag.finish()
        if hit is None or hit.action is None:
            return None
        handle, self._drag_handle = self._drag_handle, None
        if handle is not None:
            self._pending_snap = (handle, hit)
        return hit.action

    def cancel_drag(self) -> None:
        """Escape press / drag abort: drop the session without dispatching."""
        self.drag.cancel()
        self._drag_handle = None

    # ----- ActionBus draining (brief §5 #6) --------------------------

    def drain_actions(self) -> int:
        """Drain queued hotkey-triggered Actions into the dispatcher.

        Called by the Qt main thread on a timer. Returns the count drained.
        """
        if self._mousehook is not None:
            self._mousehook[1].poll()
        count = 0
        pending, self._pending_snap = self._pending_snap, None
        if pending is not None:
            handle, hit = pending
            if hit.action is not None and hit.target is not None:
                self.dispatcher.dispatch_target(handle, hit.action, hit.target)
                count = 1
        return count + self.bus.drain(self.dispatcher.dispatch, limit=16) + self.drain_workspaces()

    # ----- named workspaces -----------------------------------------

    def capture_named_workspace(self, name: str):
        """Capture visible windows, persist the workspace, and make it active."""
        workspace = capture_workspace(cast(WorkspaceWindows, self.windows), name)
        updated = deepcopy(self.settings)
        updated.workspaces = (*updated.workspaces, workspace)
        updated.active_workspace_id = workspace.id
        if self.config_store is not None:
            self.config_store.save(updated)
        self.apply_settings(updated)
        return workspace

    def apply_named_workspace(self, workspace_id: str) -> WorkspaceResult:
        workspace = next(
            (workspace for workspace in self.settings.workspaces if workspace.id == workspace_id),
            None,
        )
        if workspace is None:
            raise KeyError(f"unknown workspace: {workspace_id}")
        result = apply_workspace(cast(WorkspaceWindows, self.windows), workspace)
        self.last_workspace_result = result
        return result

    def queue_workspace(self, workspace_id: str) -> bool:
        """Non-blocking producer path used by the Win32 hotkey thread."""
        try:
            self._workspace_queue.put_nowait(workspace_id)
            return True
        except queue.Full:
            _log.warning("workspace queue full; dropped %s", workspace_id)
            return False

    def drain_workspaces(self) -> int:
        """Apply queued workspace requests on the main/Qt thread."""
        count = 0
        # Each workspace can move many windows. One per tick keeps the UI
        # responsive even while workspace shortcuts are being repeated.
        for _ in range(min(1, self._workspace_queue.qsize())):
            try:
                workspace_id = self._workspace_queue.get_nowait()
            except queue.Empty:
                return count
            try:
                self.apply_named_workspace(workspace_id)
            except Exception:  # noqa: BLE001
                _log.exception("workspace restore failed: %s", workspace_id)
            count += 1
        return count

    # ----- Drag-preview pump (brief §2 #13) --------------------------

    def drain_drag_preview(
        self,
        on_show: Callable[[Rect], None],
        on_hide: Callable[[], None],
    ) -> bool:
        """Drive the overlay from the current drag-session state.

        Called by the Qt main thread on the same timer as drain_actions.
        Polls the session for a snap hit; if one is current shows the
        overlay at the target rect, otherwise hides it. Returns True iff
        the overlay should be visible after this call.

        Hot-path safety: the callbacks only fire when the visible state
        actually changes (show with a new rect, or hide-after-show).
        Idle ticks — by far the common case at 60 Hz — do nothing.
        """
        if not self.drag.active:
            if self._preview_state is not None:
                on_hide()
                self._preview_state = None
            return False
        hit = self.drag.poll()
        if hit is not None and hit.target is not None:
            if self._preview_state != hit.target:
                on_show(hit.target)
                self._preview_state = hit.target
            return True
        if self._preview_state is not None:
            on_hide()
            self._preview_state = None
        return False

    # ----- background maintenance (called from the Qt timer) --------

    def maintenance(self, now: float | None = None) -> int:
        """Periodic upkeep: prune cycle/history entries for closed windows.

        Called from the same 16ms tick as drain_actions/drain_drag_preview.
        Internally rate-limited to once every `prune_interval` seconds —
        IsWindow() across every recorded HWND would be wasteful at 60 Hz,
        but a stale-entry sweep once a minute keeps memory bounded for a
        tray app that stays open all day (brief §5 #9, "validate with
        IsWindow(hwnd) and evict stale entries").

        Returns the count of entries pruned (0 on rate-limited calls).
        """
        import time

        t = now if now is not None else time.monotonic()
        if t - self._last_prune < self.prune_interval:
            return 0
        self._last_prune = t
        try:
            return self.dispatcher.prune_stale_state()
        except Exception:  # noqa: BLE001 — IsWindow can race; never crash the tick
            _log.debug("maintenance prune raised", exc_info=True)
            return 0

    # ----- mouse hook lifecycle (brief §2 #13, runtime toggle) -------

    def start_mousehook(self) -> bool:
        """Install the WH_MOUSE_LL hook if not already running.

        No-op when `drag_to_edge_enabled` is False, when a hook is
        already installed, or when the platform/Win32 layer rejects the
        install (logged at debug). Returns True iff a hook is active
        after this call.

        Called from `apply_settings` on the False → True drag-to-edge
        toggle so the prefs change takes effect without restart.
        """
        if self._mousehook is not None:
            return True
        if not self.settings.drag_to_edge_enabled:
            return False
        try:
            from .adapters.win32_mousehook import Win32MouseHook
        except ImportError:
            _log.debug("win32_mousehook not importable; skipping install")
            return False
        on_event, detector = make_drag_event_dispatcher(self)
        try:
            hook = Win32MouseHook(on_event=on_event)
        except Exception:  # noqa: BLE001 — install can fail on non-Windows / blocked
            _log.warning("mouse hook install failed", exc_info=True)
            return False
        self._mousehook = (hook, detector)
        # Register shutdown so app exit always unwinds — but ONLY the
        # first time. Otherwise toggling drag-to-edge N times in prefs
        # would queue N duplicate stop_mousehook calls in cleanup.
        if not self._mousehook_cleanup_registered:
            self.cleanup.register(self.stop_mousehook)
            self._mousehook_cleanup_registered = True
        return True

    def stop_mousehook(self) -> None:
        """Tear down the WH_MOUSE_LL hook if it's running. Idempotent.

        Also cancels any active drag session — otherwise disabling
        drag-to-edge mid-drag would leave `self.drag.active = True`
        with no hook left to deliver the LBUTTON_UP that would end it,
        stranding the overlay until the next drag-then-release cycle.
        """
        if self._mousehook is None:
            return
        hook, detector = self._mousehook
        self._mousehook = None
        try:
            hook.shutdown()
        except Exception:  # noqa: BLE001
            _log.warning("mouse hook shutdown raised", exc_info=True)
        try:
            detector.reset()
        except Exception:  # noqa: BLE001
            _log.debug("detector reset raised", exc_info=True)
        # Strand-proof: drop any in-flight session so drain_drag_preview
        # hides the overlay and ctx.drag.active goes back to False.
        if self.drag.active:
            self.drag.cancel()

    def shutdown(self) -> int:
        """Run every registered cleanup (brief §5 #11). Returns count."""
        return self.cleanup.run()


def build(
    settings: Settings,
    windows: WindowManager,
    *,
    hotkeys: Hotkeys | None = None,
    config_store: ConfigStore | None = None,
    autostart: AutoStart | None = None,
    autostart_command_line: str | None = None,
    single_instance: SingleInstance | None = None,
    bus: ActionBus | None = None,
    cleanup: CleanupRegistry | None = None,
    first_run: bool = False,
) -> AppContext:
    """Construct an AppContext with the supplied (typically faked) ports.

    Production code uses `bind_win32()` instead.
    """
    # Acquire the single-instance guard *before* constructing anything
    # expensive — if a second instance is detected we want to exit
    # without spinning up the dispatcher or hotkey threads.
    if single_instance is not None and not single_instance.acquire():
        raise SecondInstanceError(
            "another instance is already running — exit and surface its tray icon"
        )

    cycle = CycleState(idle_timeout=settings.cycle_idle_timeout)
    dispatcher = Dispatcher(
        windows,
        gap=settings.gap,
        cycle=cycle,
        history=History(),
        almost_maximize_scale=settings.almost_maximize_scale,
    )
    # DragSession's monitor list is refreshed in begin_drag, so an empty
    # initial list is fine — we never poll it before start().
    drag = DragSession(monitors=[], gap=settings.gap)
    ctx = AppContext(
        settings=settings,
        windows=windows,
        dispatcher=dispatcher,
        drag=drag,
        cleanup=cleanup if cleanup is not None else CleanupRegistry(),
        hotkeys=hotkeys,
        config_store=config_store,
        autostart=autostart,
        autostart_command_line=autostart_command_line,
        single_instance=single_instance,
        bus=bus if bus is not None else ActionBus(),
        first_run=first_run,
    )
    if hotkeys is not None:
        ctx.cleanup.register(hotkeys.unregister_all)
    if single_instance is not None:
        ctx.cleanup.register(single_instance.release)
    # Reconcile registry state on startup so a setting flipped while the
    # app wasn't running gets re-applied.
    ctx.sync_autostart()
    return ctx


def _bind_shortcuts(
    ctx: AppContext,
    register: Callable[[str, Callable[[], None]], int],
    dispatch: Callable[[Action], object],
) -> int:
    """Shared loop body for `bind_hotkeys` and `bind_hotkeys_via_bus`.

    Per-combo registration failures are caught + logged so one OS clash
    can't strand the rest of the keymap. Also writes a `BindingReport`
    to `ctx.last_binding_report` so the tray can render the result
    without having to peek at the win32 adapter.
    """
    bound_pairs: list[tuple[Action, str]] = []
    failed_pairs: list[tuple[Action, str, str]] = []
    workspace_bound: list[tuple[str, str, str]] = []
    workspace_failed: list[tuple[str, str, str, str]] = []
    for action, combo in ctx.settings.shortcuts.items():
        try:
            register(combo, lambda a=action: dispatch(a))
            bound_pairs.append((action, combo))
        except Exception as e:  # noqa: BLE001 — surface in UI, not as a crash
            _log.warning("failed to bind %s -> %s", action.value, combo, exc_info=True)
            failed_pairs.append((action, combo, str(e)))
    for workspace in ctx.settings.workspaces:
        combo = workspace.shortcut.strip()
        if not combo:
            continue
        try:
            register(combo, lambda workspace_id=workspace.id: ctx.queue_workspace(workspace_id))
            workspace_bound.append((workspace.id, workspace.name, combo))
        except Exception as e:  # noqa: BLE001
            _log.warning("failed to bind workspace %s -> %s", workspace.name, combo, exc_info=True)
            workspace_failed.append((workspace.id, workspace.name, combo, str(e)))
    ctx.last_binding_report = BindingReport(
        bound=tuple(bound_pairs),
        failed=tuple(failed_pairs),
        workspace_bound=tuple(workspace_bound),
        workspace_failed=tuple(workspace_failed),
    )
    return len(bound_pairs) + len(workspace_bound)


def bind_hotkeys(ctx: AppContext, register: Callable[[str, Callable[[], None]], int]) -> int:
    """Register every action's shortcut, dispatching **directly**.

    The registered callback calls `ctx.dispatcher.dispatch(action)` inline.
    This is fine for tests (the test thread IS the dispatch thread) and
    for any caller that can guarantee `register`'s callback fires on a
    thread where blocking on Win32 syscalls is OK. The production path
    uses `bind_hotkeys_via_bus()` instead — see brief §5 #6.

    `register(combo, callback)` is a closure-typed parameter (not just
    `ctx.hotkeys.register`) so a test can drop in a fake that records
    bindings without needing a Hotkeys adapter at all.

    Returns the count of successfully-bound shortcuts.
    """
    return _bind_shortcuts(ctx, register, ctx.dispatcher.dispatch)


def bind_hotkeys_via_bus(
    ctx: AppContext,
    register: Callable[[str, Callable[[], None]], int],
) -> int:
    """Like `bind_hotkeys` but routes through `ctx.bus`.

    The callback is non-blocking (ActionBus.submit is fast and
    overflow-tolerant) — safe to run on the Win32 hotkey pump thread.
    Drain with `ctx.drain_actions()` on the main thread.
    """
    return _bind_shortcuts(ctx, register, ctx.bus.submit)


def bind_win32(
    *,
    command_line: str | None = None,
    config_path: str | None = None,
) -> AppContext:
    """Production wiring — all Win32 adapters in one call.

    Order of operations:
      1. enable DPI awareness (must be first, before any HWND).
      2. acquire single-instance mutex (raises SecondInstanceError).
      3. load Settings from JSON config (fallback to defaults).
      4. construct Win32WindowManager + Win32Hotkeys + AutoStart.
      5. build() the AppContext.
      6. bind hotkeys via the ActionBus (so hotkey callbacks don't run
         dispatcher on the pump thread — brief §5 #6).
      7. register shutdown cleanup for the hotkeys thread.
    """
    # Lazy imports so the module is importable on non-Windows.
    from .adapters.json_config import JsonConfigStore
    from .adapters.single_instance import best_available as best_single
    from .adapters.win32_hotkeys import Win32Hotkeys
    from .adapters.win32_windows import Win32WindowManager
    from .adapters.win_dpi import enable_dpi_awareness
    from .adapters.winreg_autostart import best_available as best_autostart

    dpi_level = enable_dpi_awareness()
    _log.info("DPI awareness: %s", dpi_level.value)

    si = best_single()
    if not si.acquire():
        raise SecondInstanceError("another instance is already running")
    cleanup = CleanupRegistry()
    cleanup.register(si.release)
    try:
        config = JsonConfigStore() if config_path is None else JsonConfigStore(config_path)
        # Detect first-run BEFORE load() — load() tolerates a missing file by
        # returning Settings(), so once it's run we can't tell "fresh install"
        # from "user has an empty config" anymore.
        first_run = not config.path.exists()
        settings = config.load()
        # Persist defaults immediately on first launch so the user can find +
        # hand-edit the file; also flips first_run for the next start.
        if first_run:
            try:
                config.save(settings)
            except Exception:  # noqa: BLE001
                _log.warning("first-run config save failed", exc_info=True)

        windows = Win32WindowManager()
        hotkeys = Win32Hotkeys()
        cleanup.register(hotkeys.shutdown)
        autostart = best_autostart()

        ctx = build(
            settings,
            windows,
            hotkeys=hotkeys,
            config_store=config,
            autostart=autostart,
            autostart_command_line=command_line,
            cleanup=cleanup,
            first_run=first_run,
        )

        ctx.single_instance = si

        # Hotkey callbacks must not block the pump thread → route via the bus.
        bind_hotkeys_via_bus(ctx, hotkeys.register)

        # Drag-to-edge: install the low-level mouse hook and wire it through
        # the detector to the drag-snap facade. Best-effort — a hook failure
        # must not block startup (the keyboard shortcuts still work).
        try:
            bind_mousehook(ctx)
        except Exception:  # noqa: BLE001
            _log.warning("mouse hook install failed — drag-to-edge disabled", exc_info=True)

        return ctx
    except BaseException:
        cleanup.run()
        raise


class _DragInput:
    """Coalesce hook input; all native queries and drag state stay on the UI thread.

    One immutable snapshot is published per event. Reading it never clears the
    slot, so a concurrent producer cannot lose a release between read and clear.
    A complete click between UI ticks intentionally does not start a snap.
    """

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._pressed = False
        self._generation = 0
        self._latest: tuple[int, bool, int, int] | None = None
        self._consumed_generation = -1
        self._initial: Rect | None = None
        self._handle: object | None = None
        self._translated = False
        self._cancelled = False

    @property
    def state(self) -> str:
        if self._cancelled or not self._latest or not self._latest[1]:
            return "idle"
        return "dragging" if self.ctx.drag.active else "armed"

    def on_event(self, kind: str, x: int, y: int) -> None:
        # Hook thread: constant memory, no native calls, dispatch or logging.
        if kind == "lbutton_down":
            self._generation += 1
            self._pressed = True
        elif kind == "lbutton_up":
            self._pressed = False
        elif kind != "move" or not self._pressed:
            return
        self._latest = (self._generation, self._pressed, x, y)

    def reset(self) -> None:
        self.ctx.cancel_drag()
        self._handle = None
        self._initial = None
        self._translated = False
        self._cancelled = True

    def poll(self) -> None:
        snapshot = self._latest
        if snapshot is None:
            return
        generation, pressed, x, y = snapshot
        if generation != self._consumed_generation:
            self.reset()
            self._cancelled = False
            self._consumed_generation = generation
        if self._cancelled:
            return
        windows = self.ctx.windows
        try:
            if getattr(windows, "is_escape_pressed", lambda: False)():
                self.reset()
                return
            moving = getattr(windows, "get_drag_window", lambda: None)()
            if self._handle is None:
                if moving is None:
                    return  # Windows may not have processed the first movement yet.
                if classify(windows.get_window_flags(moving)) is Capability.NONE:
                    self.reset()
                    return
                self._initial = windows.get_window_rect(moving)
                self._handle = moving
                self.ctx.begin_drag(self._initial)
                self.ctx._drag_handle = moving
            elif pressed and moving != self._handle:
                self.reset()  # Escape or an aborted native move loop.
                return
            if not pressed and moving == self._handle:
                # The hook runs before the target handles mouse-up. Let its
                # native move/snap finish before applying our final rectangle.
                return
            current = windows.get_window_rect(self._handle)
            initial = self._initial
            assert initial is not None
            if pressed and (current.width, current.height) != (initial.width, initial.height):
                self.reset()  # GUI_INMOVESIZE also covers border resizing.
                return
            if pressed:
                self._translated |= (current.x, current.y) != (initial.x, initial.y)
            if self._translated:
                self.ctx.drag_update(x, y)
            if not pressed:
                if self._translated:
                    self.ctx.end_drag()
                self.reset()
        except (OSError, ValueError):
            _log.debug("native drag ended before it could be snapped", exc_info=True)
            self.reset()


def make_drag_event_dispatcher(
    ctx: AppContext,
) -> tuple[Callable[[str, int, int], None], _DragInput]:
    """Return the O(1) hook producer and main-thread drag consumer."""
    controller = _DragInput(ctx)
    return controller.on_event, controller


def bind_mousehook(ctx: AppContext) -> bool:
    """Install Win32MouseHook and route its events through a DragDetector.

    Thin wrapper over `ctx.start_mousehook()` for compatibility with the
    older startup-flow API. The lifecycle (install/uninstall + shutdown
    registration) lives on AppContext so apply_settings can flip it
    when the user toggles drag-to-edge in prefs (no restart required).

    Returns True iff the hook is now active.

    The hook only publishes an immutable input snapshot. drain_actions()
    consumes it on the main thread, including native move-loop detection,
    preview state and final placement.
    """
    return ctx.start_mousehook()
