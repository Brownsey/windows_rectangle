"""Composition root — the only place adapters get bound to ports.

`AppContext` wires Settings into a Dispatcher + CleanupRegistry. The
win32 adapters import lazily inside `bind_win32()` so that pytest on
non-Windows CI doesn't pay for pywin32/PySide6 imports just to test
core. The dispatcher itself is fully driveable via any `WindowManager`
fake, as the tests demonstrate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

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
    windows: "WindowManager"
    dispatcher: Dispatcher
    drag: DragSession
    cleanup: CleanupRegistry = field(default_factory=CleanupRegistry)
    hotkeys: "Hotkeys | None" = None
    config_store: ConfigStore | None = None
    autostart: "AutoStart | None" = None
    autostart_command_line: str | None = None
    single_instance: "SingleInstance | None" = None
    bus: ActionBus = field(default_factory=ActionBus)

    def apply_settings(self, settings: Settings) -> None:
        """Mutate the live dispatcher to reflect new user settings.

        Used by the prefs UI after `ConfigStore.save(...)`.
        """
        self.settings = settings
        self.dispatcher.gap = settings.gap
        # Cycle idle timeout is on the CycleState, not the Dispatcher.
        # The dispatcher uses whichever CycleState we gave it.
        self.dispatcher._cycle.idle_timeout = settings.cycle_idle_timeout
        self.drag.gap = settings.gap
        self.sync_autostart()

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

    def shutdown(self) -> int:
        """Run every registered cleanup (brief §5 #11). Returns count."""
        return self.cleanup.run()


def build(
    settings: Settings,
    windows: "WindowManager",
    *,
    hotkeys: "Hotkeys | None" = None,
    config_store: ConfigStore | None = None,
    autostart: "AutoStart | None" = None,
    autostart_command_line: str | None = None,
    single_instance: "SingleInstance | None" = None,
    bus: ActionBus | None = None,
    cleanup: CleanupRegistry | None = None,
) -> AppContext:
    """Construct an AppContext with the supplied (typically faked) ports.

    Production code uses `bind_win32()` instead.
    """
    # Acquire the single-instance guard *before* constructing anything
    # expensive — if a second instance is detected we want to exit
    # without spinning up the dispatcher or hotkey threads.
    if single_instance is not None:
        if not single_instance.acquire():
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
    config_path: "str | None" = None,
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
    return ctx
