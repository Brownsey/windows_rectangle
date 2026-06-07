"""Tests for windows_rectangle.app composition root."""

from collections.abc import Callable

import pytest

from windows_rectangle.app import (
    SecondInstanceError,
    bind_hotkeys,
    bind_hotkeys_via_bus,
    build,
)
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.cleanup import CleanupRegistry
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings

from .conftest import FakeWindowManager, make_monitor

M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)


class FakeHotkeys:
    def __init__(self):
        self.registered: dict[int, tuple[str, Callable[[], None]]] = {}
        self._next = 0
        self.unregister_all_calls = 0

    def register(self, combo, callback):
        self._next += 1
        self.registered[self._next] = (combo, callback)
        return self._next

    def unregister(self, hotkey_id):
        self.registered.pop(hotkey_id, None)

    def unregister_all(self):
        self.unregister_all_calls += 1
        self.registered.clear()


@pytest.fixture
def windows():
    wm = FakeWindowManager(monitors=[M1])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    return wm


def test_build_creates_dispatcher_with_settings_gap(windows):
    ctx = build(Settings(gap=15), windows)
    assert ctx.dispatcher.gap == 15


def test_build_sets_cycle_idle_timeout(windows):
    ctx = build(Settings(cycle_idle_timeout=3.0), windows)
    # The Dispatcher uses the CycleState we passed.
    assert ctx.dispatcher._cycle.idle_timeout == 3.0


def test_dispatcher_routes_through_app_context(windows):
    ctx = build(Settings(), windows)
    result = ctx.dispatcher.dispatch(Action.LEFT_HALF)
    assert result.moved
    # M1 work area is 1920x1040; left-half = 960x1040 at x=0
    assert windows.windows[101] == Rect(0, 0, 960, 1040)


def test_apply_settings_updates_gap_live(windows):
    ctx = build(Settings(gap=0), windows)
    ctx.apply_settings(Settings(gap=20))
    assert ctx.dispatcher.gap == 20


def test_apply_settings_updates_cycle_timeout(windows):
    ctx = build(Settings(cycle_idle_timeout=1.0), windows)
    ctx.apply_settings(Settings(cycle_idle_timeout=5.5))
    assert ctx.dispatcher._cycle.idle_timeout == 5.5


def test_shutdown_runs_cleanup(windows):
    log = []
    cleanup = CleanupRegistry()
    cleanup.register(lambda: log.append("done"))
    ctx = build(Settings(), windows, cleanup=cleanup)
    assert ctx.shutdown() == 1
    assert log == ["done"]


def test_shutdown_idempotent(windows):
    ctx = build(Settings(), windows)
    assert ctx.shutdown() == 0
    assert ctx.shutdown() == 0


def test_hotkeys_unregister_all_on_shutdown(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    ctx.shutdown()
    assert hot.unregister_all_calls == 1


def test_bind_hotkeys_registers_every_action(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bound = bind_hotkeys(ctx, hot.register)
    assert bound == len(DEFAULT_SHORTCUTS)
    assert len(hot.registered) == len(DEFAULT_SHORTCUTS)


def test_bind_hotkeys_dispatches_through_callback(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys(ctx, hot.register)
    # Find the LEFT_HALF combo's callback and invoke it.
    left_combo = DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    callback = next(cb for combo, cb in hot.registered.values() if combo == left_combo)
    callback()
    assert windows.windows[101] == Rect(0, 0, 960, 1040)


def test_apply_settings_rebinds_when_shortcuts_changed(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    n_before = len(hot.registered)
    # Change one shortcut and apply.
    new_shortcuts = dict(ctx.settings.shortcuts)
    new_shortcuts[Action.LEFT_HALF] = "ctrl+shift+left"
    ctx.apply_settings(Settings(shortcuts=new_shortcuts))
    # One unregister_all (clear), then a fresh full re-bind.
    assert hot.unregister_all_calls >= 1
    # All combos re-registered after the unregister.
    assert len(hot.registered) == n_before
    # The new combo for LEFT_HALF is now in the registered set.
    combos_now = {c for c, _cb in hot.registered.values()}
    assert "ctrl+shift+left" in combos_now


def test_apply_settings_does_not_rebind_when_shortcuts_unchanged(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    # Change something *other* than shortcuts.
    ctx.apply_settings(Settings(shortcuts=dict(ctx.settings.shortcuts), gap=42))
    assert hot.unregister_all_calls == 0  # no rebind triggered


def test_rebind_hotkeys_no_hotkeys_adapter_is_noop(windows):
    ctx = build(Settings(), windows)  # no hotkeys wired
    assert ctx.rebind_hotkeys() == 0


def test_rebind_hotkeys_returns_count_of_bindings(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bound = ctx.rebind_hotkeys()
    assert bound == len(ctx.settings.shortcuts)


def test_bind_hotkeys_tolerates_individual_failures(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    calls = []

    def register(combo, cb):
        calls.append(combo)
        if "ctrl+alt+left" in combo:
            raise RuntimeError("clash")
        return len(calls)

    bound = bind_hotkeys(ctx, register)
    # One failure → bound = total - 1.
    assert bound == len(DEFAULT_SHORTCUTS) - 1


# ----- DragSession facade (brief §2 #13) ----------------------------

def test_begin_drag_refreshes_monitor_list(windows):
    ctx = build(Settings(), windows)
    # Drag session starts with empty monitors; begin_drag should refresh.
    assert ctx.drag.monitors == []
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert len(ctx.drag.monitors) == 1
    assert ctx.drag.active


def test_begin_drag_respects_disable_setting(windows):
    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert not ctx.drag.active


def test_end_drag_dispatches_when_zone_held(windows, monkeypatch):
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    # Drive a left-edge mouse position through poll() to cache a hit.
    ctx.drag_update(2, 540)
    # Force throttle to allow.
    ctx.drag._throttle.reset()
    ctx.drag_poll()
    action = ctx.end_drag()
    assert action is Action.LEFT_HALF
    # Window was dispatched to left half (work area 1920x1040).
    assert windows.windows[101] == Rect(0, 0, 960, 1040)


def test_end_drag_without_zone_returns_none(windows):
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    # No mouse updates → no hit.
    assert ctx.end_drag() is None


def test_cancel_drag_clears_without_dispatching(windows):
    ctx = build(Settings(), windows)
    original = windows.windows[101]
    ctx.begin_drag(original)
    ctx.drag_update(2, 540)
    ctx.drag._throttle.reset()
    ctx.drag_poll()
    ctx.cancel_drag()
    assert not ctx.drag.active
    assert windows.windows[101] == original  # unchanged


def test_begin_drag_for_active_window_starts_session(windows):
    ctx = build(Settings(), windows)
    started = ctx.begin_drag_for_active_window()
    assert started
    assert ctx.drag.active


def test_begin_drag_for_active_window_returns_false_when_disabled(windows):
    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    assert ctx.begin_drag_for_active_window() is False
    assert not ctx.drag.active


def test_begin_drag_for_active_window_returns_false_when_no_active(windows):
    windows.active = None
    ctx = build(Settings(), windows)
    assert ctx.begin_drag_for_active_window() is False
    assert not ctx.drag.active


def test_drain_drag_preview_inactive_session_is_noop_when_already_hidden(windows):
    """Idle ticks (drag inactive, overlay already hidden) must NOT fire
    callbacks — we tick 60×/s and Qt repaints add up."""
    ctx = build(Settings(), windows)
    shown: list = []
    hidden: list = []
    visible = ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert visible is False
    assert shown == []
    assert hidden == []


def test_drain_drag_preview_active_no_hit_is_noop(windows):
    """Active drag but cursor not in a zone → still no callbacks since
    the overlay was never shown."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    shown: list = []
    hidden: list = []
    visible = ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert visible is False
    assert shown == []
    assert hidden == []


def test_drain_drag_preview_active_with_hit_shows(windows):
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)              # left edge
    ctx.drag._throttle.reset()           # allow poll
    shown: list = []
    hidden: list = []
    visible = ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert visible is True
    assert hidden == []
    assert len(shown) == 1
    assert shown[0] == Rect(0, 0, 960, 1040)


def test_drain_drag_preview_dedup_same_rect(windows):
    """Two consecutive ticks at the same snap target → on_show fires once."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)
    ctx.drag._throttle.reset()
    shown: list = []
    hidden: list = []

    def go():
        return ctx.drain_drag_preview(
            on_show=lambda r: shown.append(r),
            on_hide=lambda: hidden.append(True),
        )

    assert go() is True
    # Throttle ticks won't change the cached hit. Push the same coord
    # again to ensure the second poll has fresh data.
    ctx.drag_update(2, 540)
    ctx.drag._throttle.reset()
    assert go() is True

    assert len(shown) == 1   # de-dup'd
    assert hidden == []


def test_drain_drag_preview_hides_once_after_being_shown(windows):
    """Show, then cursor leaves zone → exactly one on_hide fires; further
    idle ticks emit nothing."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)              # left edge → hit
    ctx.drag._throttle.reset()
    shown: list = []
    hidden: list = []
    ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert len(shown) == 1

    # Cancel the session → drag inactive again; the show-state must clear.
    ctx.cancel_drag()
    ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert hidden == [True]

    # Idle tick: no new hide.
    ctx.drain_drag_preview(
        on_show=lambda r: shown.append(r),
        on_hide=lambda: hidden.append(True),
    )
    assert hidden == [True]


def test_drain_drag_preview_fires_show_again_on_different_rect(windows):
    """Cursor moves to a different snap zone → new on_show with new rect."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    shown: list = []
    hidden: list = []

    def tick():
        return ctx.drain_drag_preview(
            on_show=lambda r: shown.append(r),
            on_hide=lambda: hidden.append(True),
        )

    # First hit: left edge.
    ctx.drag_update(2, 540)
    ctx.drag._throttle.reset()
    tick()

    # Second hit: right edge — different target rect.
    ctx.drag_update(1918, 540)
    ctx.drag._throttle.reset()
    tick()

    assert len(shown) == 2
    assert shown[0] != shown[1]


def test_begin_drag_for_active_window_handles_rect_lookup_failure():
    """If the adapter raises looking up the window rect (e.g. window
    closed between get_active_window and get_window_rect), we treat it
    as 'no eligible window' and return False rather than crashing."""

    class RaisingWM(FakeWindowManager):
        def get_window_rect(self, handle):
            raise OSError("window vanished")

    wm = RaisingWM(monitors=[M1])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    ctx = build(Settings(), wm)
    assert ctx.begin_drag_for_active_window() is False
    assert not ctx.drag.active


def test_apply_settings_propagates_gap_to_drag(windows):
    ctx = build(Settings(gap=0), windows)
    ctx.apply_settings(Settings(gap=12))
    assert ctx.drag.gap == 12


# ----- AutoStart wiring (brief §2 #16) ------------------------------

def test_build_syncs_autostart_to_settings_true(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart
    a = MemoryAutoStart()
    build(Settings(launch_at_login=True), windows,
          autostart=a, autostart_command_line=r"C:\app.exe")
    assert a.is_enabled()
    assert a.command_line == r"C:\app.exe"


def test_build_syncs_autostart_to_settings_false(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart
    a = MemoryAutoStart(enabled=True, command_line=r"C:\old.exe")
    build(Settings(launch_at_login=False), windows,
          autostart=a, autostart_command_line=r"C:\app.exe")
    assert not a.is_enabled()


def test_apply_settings_toggles_autostart(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart
    a = MemoryAutoStart()
    ctx = build(Settings(launch_at_login=False), windows,
                autostart=a, autostart_command_line=r"C:\app.exe")
    assert not a.is_enabled()
    ctx.apply_settings(Settings(launch_at_login=True))
    assert a.is_enabled()
    ctx.apply_settings(Settings(launch_at_login=False))
    assert not a.is_enabled()


def test_sync_autostart_noop_without_command_line(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart
    a = MemoryAutoStart()
    # No command_line supplied → sync should do nothing.
    ctx = build(Settings(launch_at_login=True), windows, autostart=a)
    assert not a.is_enabled()


def test_autostart_failure_does_not_crash(windows):
    class BrokenAutoStart:
        def is_enabled(self): raise OSError("registry hosed")
        def enable(self, cl): raise OSError("nope")
        def disable(self): raise OSError("nope")
    # Should log + swallow — not raise.
    build(Settings(launch_at_login=True), windows,
          autostart=BrokenAutoStart(), autostart_command_line=r"C:\app.exe")


# ----- SingleInstance wiring (brief §6) -----------------------------

def test_build_with_unheld_single_instance_acquires(windows):
    from windows_rectangle.adapters.single_instance import MemorySingleInstance
    MemorySingleInstance._held.clear()
    si = MemorySingleInstance("Local\\TestApp")
    ctx = build(Settings(), windows, single_instance=si)
    assert ctx.single_instance is si
    # Lock was acquired.
    assert "Local\\TestApp" in MemorySingleInstance._held
    MemorySingleInstance._held.clear()


def test_build_with_held_single_instance_raises(windows):
    from windows_rectangle.adapters.single_instance import MemorySingleInstance
    MemorySingleInstance._held.clear()
    first = MemorySingleInstance("Local\\TestApp")
    first.acquire()
    second = MemorySingleInstance("Local\\TestApp")
    with pytest.raises(SecondInstanceError):
        build(Settings(), windows, single_instance=second)
    first.release()
    MemorySingleInstance._held.clear()


def test_shutdown_releases_single_instance(windows):
    from windows_rectangle.adapters.single_instance import MemorySingleInstance
    MemorySingleInstance._held.clear()
    si = MemorySingleInstance("Local\\TestApp")
    ctx = build(Settings(), windows, single_instance=si)
    assert "Local\\TestApp" in MemorySingleInstance._held
    ctx.shutdown()
    assert "Local\\TestApp" not in MemorySingleInstance._held


# ----- ActionBus wiring (brief §5 #6) -------------------------------

def test_default_bus_is_constructed(windows):
    ctx = build(Settings(), windows)
    assert ctx.bus is not None
    assert ctx.bus.pending() == 0


def test_bind_hotkeys_via_bus_submits_actions(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bound = bind_hotkeys_via_bus(ctx, hot.register)
    assert bound == len(DEFAULT_SHORTCUTS)
    # Fire a callback — it should land on the bus, not dispatch directly.
    cb = next(iter(hot.registered.values()))[1]
    cb()
    assert ctx.bus.pending() == 1
    # The active window should NOT have been moved yet.
    assert windows.move_log == []


def test_drain_actions_dispatches_pending(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    # Find the LEFT_HALF callback and fire it.
    combo = DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    cb = next(c for cmb, c in hot.registered.values() if cmb == combo)
    cb()
    # Drain — now the dispatcher runs.
    count = ctx.drain_actions()
    assert count == 1
    assert windows.windows[101] == Rect(0, 0, 960, 1040)
