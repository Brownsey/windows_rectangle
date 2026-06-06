"""Tests for windows_rectangle.app composition root."""

from typing import Callable

import pytest

from windows_rectangle.app import AppContext, bind_hotkeys, build
from windows_rectangle.core.actions import Action, DEFAULT_SHORTCUTS
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
