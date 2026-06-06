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
