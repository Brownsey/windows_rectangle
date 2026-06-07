"""Composition root — the only place adapters get bound to ports.

`AppContext` wires Settings into a Dispatcher + CleanupRegistry. The
win32 adapters import lazily inside `bind_win32()` so that pytest on
non-Windows CI doesn't pay for pywin32/PySide6 imports just to test
core. The dispatcher itself is fully driveable via any `WindowManager`
fake, as the tests demonstrate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .core.actionbus import ActionBus
from .core.actions import Action
from .core.cleanup import CleanupRegistry
from .core.cycle import CycleState
from .core.dispatcher import Dispatcher
from .core.dragsession import DragSession
from .core.geometry import Rect
from .core.history import History
from .core.snap import SnapHit
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

    def apply_settings(self, settings: Settings) -> None:
        """Mutate the live dispatcher to reflect new user settings.

        Used by the prefs UI after `ConfigStore.save(...)`. If the user
        rebound any shortcuts, we re-register them with the hotkeys
        adapter so the new combos take effect without a restart (brief
        note: "all shortcuts can be configured... those shortcuts work").
        """
        shortcuts_changed = settings.shortcuts != self.settings.shortcuts
        self.settings = settings
        self.dispatcher.gap = settings.gap
        # Cycle idle timeout is on the CycleState, not the Dispatcher.
        # The dispatcher uses whichever CycleState we gave it.
        self.dispatcher._cycle.idle_timeout = settings.cycle_idle_timeout
        self.drag.gap = settings.gap
        if shortcuts_changed and self.hotkeys is not None:
            self.rebind_hotkeys()
        self.sync_autostart()

    def rebind_hotkeys(self) -> int:
        """Unregister every hotkey and re-register from `self.settings.shortcuts`.

        Returns the count of successful (re-)registrations. No-op if no
        hotkeys adapter is wired. Failures of individual combos are
        tolerated — the prefs UI surfaces them as warnings before commit,
        and an OS-clash here is logged but doesn't break the rebind.
        """
        if self.hotkeys is None:
            return 0
        self.hotkeys.unregister_all()
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
        Returns the dispatched Action so callers can show feedback.
        """
        hit = self.drag.finish()
        if hit is None or hit.action is None:
            return None
        self.dispatcher.dispatch(hit.action)
        return hit.action

    def cancel_drag(self) -> None:
        """Escape press / drag abort: drop the session without dispatching."""
        self.drag.cancel()

    # ----- ActionBus draining (brief §5 #6) --------------------------

    def drain_actions(self) -> int:
        """Drain queued hotkey-triggered Actions into the dispatcher.

        Called by the Qt main thread on a timer. Returns the count drained.
        """
        return self.bus.drain(self.dispatcher.dispatch)

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
        the overlay should be visible after this call — useful for tests
        and for the caller to short-circuit redundant Qt redraws.

        Hot-path safety: when no drag session is active, this returns
        immediately without allocating or polling — the timer ticks 60×/s
        most of the time idle, so the no-op path matters.
        """
        if not self.drag.active:
            on_hide()
            return False
        hit = self.drag.poll()
        if hit is not None and hit.target is not None:
            on_show(hit.target)
            return True
        on_hide()
        return False

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
    )
    if hotkeys is not None:
        ctx.cleanup.register(hotkeys.unregister_all)
    if single_instance is not None:
        ctx.cleanup.register(single_instance.release)
    # Reconcile registry state on startup so a setting flipped while the
    # app wasn't running gets re-applied.
    ctx.sync_autostart()
    return ctx


def bind_hotkeys(ctx: AppContext, register: Callable[[str, Callable[[], None]], int]) -> int:
    """Register every action's shortcut via the supplied callback.

    `register(combo, callback)` typically wraps `ctx.hotkeys.register(...)`
    but kept as a callable so the prefs UI can use the same wiring for
    a live re-bind preview.

    Returns the count of successfully-bound shortcuts.

    The callback dispatches directly. For production use (hotkeys fire on
    a separate thread), prefer `bind_hotkeys_via_bus()` which submits onto
    `ctx.bus` so the dispatcher only runs on the main thread (brief §5 #6).
    """
    bound = 0
    for action, combo in ctx.settings.shortcuts.items():
        try:
            register(combo, lambda a=action: ctx.dispatcher.dispatch(a))
            bound += 1
        except Exception:  # noqa: BLE001 — surface in UI, not as a crash
            _log.warning("failed to bind %s -> %s", action.value, combo, exc_info=True)
    return bound


def bind_hotkeys_via_bus(ctx: AppContext,
                         register: Callable[[str, Callable[[], None]], int]) -> int:
    """Like `bind_hotkeys` but routes through `ctx.bus`.

    The callback is non-blocking (ActionBus.submit is fast and
    overflow-tolerant) — safe to run on the Win32 hotkey pump thread.
    Drain with `ctx.drain_actions()` on the main thread.
    """
    bound = 0
    for action, combo in ctx.settings.shortcuts.items():
        try:
            register(combo, lambda a=action: ctx.bus.submit(a))
            bound += 1
        except Exception:  # noqa: BLE001
            _log.warning("failed to bind %s -> %s", action.value, combo, exc_info=True)
    return bound


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
    config = JsonConfigStore() if config_path is None else JsonConfigStore(config_path)
    settings = config.load()

    windows = Win32WindowManager()
    hotkeys = Win32Hotkeys()
    autostart = best_autostart()

    ctx = build(
        settings,
        windows,
        hotkeys=hotkeys,
        config_store=config,
        autostart=autostart,
        autostart_command_line=command_line,
        single_instance=si,
    )

    # Hotkey callbacks must not block the pump thread → route via the bus.
    bind_hotkeys_via_bus(ctx, hotkeys.register)

    # Tear down the hotkey pump on shutdown.
    ctx.cleanup.register(hotkeys.shutdown)

    # Drag-to-edge: install the low-level mouse hook and wire it through
    # the detector to the drag-snap facade. Best-effort — a hook failure
    # must not block startup (the keyboard shortcuts still work).
    try:
        bind_mousehook(ctx)
    except Exception:  # noqa: BLE001
        _log.warning("mouse hook install failed — drag-to-edge disabled", exc_info=True)

    return ctx


def bind_mousehook(ctx: AppContext) -> None:
    """Install Win32MouseHook and route its events through a DragDetector
    into `ctx`'s drag-snap facade. Registers shutdown in `ctx.cleanup`.

    The detector's `on_begin` calls back into the WindowManager on the
    hook thread to look up the active window. That's a fast read of
    GetForegroundWindow / GetWindowRect — well within the WH_MOUSE_LL
    latency budget (brief §5 #7).

    Update + end run on the hook thread too. `drag.update()` only sets
    a LatestValue (O(1), brief §5 #7). `end_drag()` calls the dispatcher,
    which could be expensive — in production __main__ wraps end with an
    ActionBus.submit so the dispatch lands on the Qt thread.
    """
    from .adapters.win32_mousehook import (
        EVENT_LBUTTON_DOWN,
        EVENT_LBUTTON_UP,
        EVENT_MOVE,
        Win32MouseHook,
    )
    from .core.dragdetector import DragDetector

    detector = DragDetector(
        on_begin=lambda x, y: ctx.begin_drag_for_active_window(),
        on_update=ctx.drag_update,
        on_end=lambda: ctx.end_drag(),
    )

    def on_event(kind: str, x: int, y: int) -> None:
        if kind == EVENT_MOVE:
            detector.on_move(x, y)
        elif kind == EVENT_LBUTTON_DOWN:
            detector.on_button_down(x, y)
        elif kind == EVENT_LBUTTON_UP:
            detector.on_button_up(x, y)

    hook = Win32MouseHook(on_event=on_event)
    ctx.cleanup.register(hook.shutdown)
    ctx.cleanup.register(detector.reset)
