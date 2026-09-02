"""Tests for windows_rectangle.app composition root."""

import os
from collections.abc import Callable
from pathlib import Path

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
from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
)
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


def test_build_first_run_defaults_to_false(windows):
    """No on-disk detection in `build` — the default keeps repeat launches
    quiet. Only bind_win32 flips this based on config-file presence."""
    ctx = build(Settings(), windows)
    assert ctx.first_run is False


def test_build_propagates_explicit_first_run_flag(windows):
    ctx = build(Settings(), windows, first_run=True)
    assert ctx.first_run is True


class _FakeConfigStore:
    """In-memory ConfigStore + a stub `.path` attr for config_folder()."""

    def __init__(self, settings, *, path=None):
        self.next = settings
        self.path = path
        self.loads = 0
        self.saves: list = []

    def load(self):
        self.loads += 1
        return self.next

    def save(self, settings):
        self.saves.append(settings)


def test_reload_config_returns_false_without_store(windows):
    ctx = build(Settings(), windows)
    assert ctx.reload_config() is False


def test_reload_config_applies_loaded_settings(windows):
    store = _FakeConfigStore(Settings(gap=42))
    ctx = build(Settings(gap=0), windows, config_store=store)
    assert ctx.reload_config() is True
    assert ctx.settings.gap == 42
    # Dispatcher also reflects the reloaded value, otherwise the reload
    # doesn't actually take effect.
    assert ctx.dispatcher.gap == 42


def test_reload_config_returns_false_when_load_raises(windows):
    class Boom:
        path = None

        def load(self):
            raise RuntimeError("kaboom")

        def save(self, settings):
            pass

    ctx = build(Settings(gap=7), windows, config_store=Boom())
    assert ctx.reload_config() is False
    # Settings stay untouched after a failed reload.
    assert ctx.settings.gap == 7


def test_config_folder_none_without_store(windows):
    ctx = build(Settings(), windows)
    assert ctx.config_folder() is None


def test_config_folder_returns_parent_of_path(windows, tmp_path):
    cfg_path = tmp_path / "windows_rectangle" / "config.json"
    store = _FakeConfigStore(Settings(), path=cfg_path)
    ctx = build(Settings(), windows, config_store=store)
    assert ctx.config_folder() == str(cfg_path.parent)


def test_config_folder_none_when_store_has_no_path(windows):
    class PathlessStore:
        def load(self):
            return Settings()

        def save(self, s):
            pass

    ctx = build(Settings(), windows, config_store=PathlessStore())
    assert ctx.config_folder() is None


def test_log_file_path_returns_str_under_appdata(windows, monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    ctx = build(Settings(), windows)
    p = ctx.log_file_path()
    assert p is not None
    assert "windows_rectangle.log" in p
    # Path-shaped — useful for the "Open log…" tray click.
    assert "windows_rectangle" in p


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


def test_build_threads_almost_maximize_scale_into_dispatcher(windows):
    ctx = build(Settings(almost_maximize_scale=0.5), windows)
    assert ctx.dispatcher.almost_maximize_scale == 0.5


def test_apply_settings_updates_almost_maximize_scale(windows):
    ctx = build(Settings(almost_maximize_scale=0.85), windows)
    ctx.apply_settings(Settings(almost_maximize_scale=0.5))
    assert ctx.dispatcher.almost_maximize_scale == 0.5
    # And the next ALMOST_MAXIMIZE dispatch uses 0.5, not 0.85.
    ctx.dispatcher.dispatch(Action.ALMOST_MAXIMIZE)
    # Work area 1920×1040; 50% = 960×520.
    r = windows.windows[101]
    assert r.width == int(1920 * 0.5)
    assert r.height == int(1040 * 0.5)


def test_apply_settings_toggles_drag_to_edge_enabled(windows):
    """drag_to_edge_enabled lives only on self.settings (begin_drag reads
    it each call); a toggle via apply_settings must take effect on the
    NEXT begin_drag, no restart required."""
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert ctx.drag.active

    ctx.cancel_drag()
    ctx.apply_settings(Settings(drag_to_edge_enabled=False))
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert not ctx.drag.active


class _FakeMouseHook:
    """Stand-in for Win32MouseHook usable on non-Windows hosts."""

    instances: list = []

    def __init__(self, on_event):
        self.on_event = on_event
        self.shutdown_called = False
        _FakeMouseHook.instances.append(self)

    def shutdown(self):
        self.shutdown_called = True


def _install_fake_mousehook(monkeypatch):
    """Patch the lazy import inside AppContext.start_mousehook."""
    import windows_rectangle.adapters.win32_mousehook as adapter_mod

    monkeypatch.setattr(adapter_mod, "Win32MouseHook", _FakeMouseHook)
    _FakeMouseHook.instances.clear()


def test_start_mousehook_skipped_when_drag_disabled(windows):
    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    assert ctx.start_mousehook() is False
    assert ctx._mousehook is None


def test_start_mousehook_installs_when_enabled(windows, monkeypatch):
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    assert ctx.start_mousehook() is True
    assert ctx._mousehook is not None
    assert len(_FakeMouseHook.instances) == 1


def test_start_mousehook_is_idempotent(windows, monkeypatch):
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.start_mousehook()
    ctx.start_mousehook()
    ctx.start_mousehook()
    # Only one hook ever constructed.
    assert len(_FakeMouseHook.instances) == 1


def test_stop_mousehook_shuts_down_hook(windows, monkeypatch):
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.start_mousehook()
    hook = _FakeMouseHook.instances[-1]
    ctx.stop_mousehook()
    assert hook.shutdown_called
    assert ctx._mousehook is None


def test_stop_mousehook_is_idempotent_when_no_hook(windows):
    ctx = build(Settings(), windows)
    ctx.stop_mousehook()  # must not raise
    ctx.stop_mousehook()


def test_apply_settings_installs_hook_on_drag_re_enable(windows, monkeypatch):
    """The headline fix: starting with drag_to_edge_enabled=False, no
    hook is installed. After apply_settings flips to True, the hook IS
    installed — no restart needed."""
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    assert ctx._mousehook is None
    ctx.apply_settings(Settings(drag_to_edge_enabled=True))
    assert ctx._mousehook is not None


def test_apply_settings_uninstalls_hook_on_drag_disable(windows, monkeypatch):
    """And the opposite direction: disabling tears the hook down."""
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.start_mousehook()
    hook = _FakeMouseHook.instances[-1]
    ctx.apply_settings(Settings(drag_to_edge_enabled=False))
    assert hook.shutdown_called
    assert ctx._mousehook is None


def test_shutdown_tears_down_running_mousehook(windows, monkeypatch):
    """ctx.shutdown() running cleanup must unwind a live hook (brief §5
    #11 — leaked WH_MOUSE_LL degrades the whole OS)."""
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.start_mousehook()
    hook = _FakeMouseHook.instances[-1]
    ctx.shutdown()
    assert hook.shutdown_called


def test_stop_mousehook_cancels_active_drag_session(windows, monkeypatch):
    """If the user disables drag-to-edge while a drag is in progress,
    stopping the hook must also cancel the session — otherwise
    self.drag.active stays True with no LBUTTON_UP coming to clear it."""
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    ctx.start_mousehook()
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert ctx.drag.active

    ctx.stop_mousehook()
    assert not ctx.drag.active


def test_mousehook_toggles_do_not_grow_cleanup(windows, monkeypatch):
    """Toggling drag-to-edge N times must only ever push one
    stop_mousehook handler into ctx.cleanup. Otherwise a chatty user
    would queue N duplicate shutdowns over an app session."""
    _install_fake_mousehook(monkeypatch)
    ctx = build(Settings(drag_to_edge_enabled=True), windows)
    before = len(list(ctx.cleanup))
    for _ in range(5):
        ctx.start_mousehook()
        ctx.stop_mousehook()
    # Across 5 full start/stop cycles, exactly one stop_mousehook entry
    # got registered (on the first install).
    assert len(list(ctx.cleanup)) - before == 1


def test_apply_settings_drag_re_enable_takes_effect_without_restart(windows):
    """The opposite toggle direction: False → True. begin_drag reads
    ctx.settings.drag_to_edge_enabled on every call, so flipping it
    via apply_settings must let begin_drag start a session.

    Iter 66 also wires the WH_MOUSE_LL hook lifecycle through
    apply_settings — see test_apply_settings_installs_hook_on_drag_re_enable
    — so the end-to-end flow (prefs flip → mouse events arrive → drag
    snaps) now works without restart.
    """
    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert not ctx.drag.active

    ctx.apply_settings(Settings(drag_to_edge_enabled=True))
    ctx.begin_drag(Rect(100, 100, 800, 600))
    assert ctx.drag.active


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


def test_bind_hotkeys_skips_blank_shortcuts(windows):
    settings = Settings(shortcuts={Action.LEFT_HALF: ""})
    hot = FakeHotkeys()
    ctx = build(settings, windows, hotkeys=hot)

    assert bind_hotkeys(ctx, hot.register) == 0
    assert hot.registered == {}
    assert ctx.last_binding_report.failed == ()


def test_workspace_shortcut_queues_restore_for_main_thread(windows):
    workspace = Workspace(
        "office",
        "Office",
        (
            WorkspacePlacement(
                "app",
                "App",
                WindowMatcher(process_name="app.exe"),
                NormalizedRect(0, 0, 5000, 10000),
            ),
        ),
        "ctrl+alt+1",
    )
    settings = Settings(workspaces=(workspace,))
    ctx = build(settings, windows)
    hot = FakeHotkeys()
    bound = bind_hotkeys_via_bus(ctx, hot.register)
    assert bound == len(DEFAULT_SHORTCUTS) + 1
    workspace_callback = next(cb for combo, cb in hot.registered.values() if combo == "ctrl+alt+1")
    workspace_callback()
    assert ctx._workspace_queue.qsize() == 1
    assert len(hot.registered) == len(DEFAULT_SHORTCUTS) + 1


def test_workspace_restore_runs_off_main_thread(windows, monkeypatch):
    import threading

    import windows_rectangle.app as app_module
    from windows_rectangle.core.workspace_service import PlacementResult, WorkspaceResult

    workspace = Workspace("office", "Office", ())
    ctx = build(Settings(workspaces=(workspace,)), windows)
    started = threading.Event()
    release = threading.Event()
    result = WorkspaceResult((PlacementResult("app", "moved"),))

    def fake_restore(_manager, _workspace):
        started.set()
        assert release.wait(2)
        return result

    monkeypatch.setattr(app_module, "launch_and_apply_workspace", fake_restore)
    assert ctx.queue_workspace("office")

    assert ctx.drain_workspaces() == 1
    assert started.wait(1)
    assert ctx.last_workspace_result is None

    release.set()
    assert ctx.wait_for_workspace_restores(timeout=2)
    assert ctx.drain_workspace_results() == 1
    assert ctx.last_workspace_result is result


def test_workspace_restores_are_globally_serialized(windows, monkeypatch):
    import threading

    import windows_rectangle.app as app_module
    from windows_rectangle.core.workspace_service import WorkspaceResult

    first = Workspace("first", "First", ())
    second = Workspace("second", "Second", ())
    ctx = build(Settings(workspaces=(first, second)), windows)
    started = threading.Event()
    release = threading.Event()

    def fake_restore(_manager, _workspace):
        started.set()
        assert release.wait(2)
        return WorkspaceResult(())

    monkeypatch.setattr(app_module, "launch_and_apply_workspace", fake_restore)
    assert ctx.queue_workspace("first")
    assert ctx.drain_workspaces() == 1
    assert started.wait(1)

    assert not ctx.queue_workspace("second")

    release.set()
    assert ctx.wait_for_workspace_restores(timeout=2)


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


def test_rebind_hotkeys_tolerates_unregister_all_failure(windows):
    """If unregister_all raises (Win32 pump thread in a bad state),
    rebind still attempts to register the new bindings."""

    class _FlakyUnregister(FakeHotkeys):
        def unregister_all(self):
            raise RuntimeError("pump thread is sulking")

    hot = _FlakyUnregister()
    ctx = build(Settings(), windows, hotkeys=hot)
    bound = ctx.rebind_hotkeys()
    # All shortcuts re-registered despite the unregister failure.
    assert bound == len(ctx.settings.shortcuts)


def test_rebind_hotkeys_no_hotkeys_adapter_is_noop(windows):
    ctx = build(Settings(), windows)  # no hotkeys wired
    assert ctx.rebind_hotkeys() == 0


def test_rebind_hotkeys_returns_count_of_bindings(windows):
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bound = ctx.rebind_hotkeys()
    assert bound == len(ctx.settings.shortcuts)


def test_clearing_a_shortcut_via_apply_settings_unregisters_it(windows):
    """End-to-end: a Settings whose shortcuts dict is missing an action
    (i.e. the user used prefs to clear it) → apply_settings rebinds
    the smaller set → that action's combo is NO LONGER registered."""
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    n_before = len(hot.registered)
    # Build the post-clear Settings: every action EXCEPT LEFT_HALF.
    smaller_shortcuts = {
        a: c for a, c in ctx.settings.shortcuts.items() if a is not Action.LEFT_HALF
    }
    ctx.apply_settings(Settings(shortcuts=smaller_shortcuts))
    # After the rebind, exactly one fewer combo is registered.
    assert len(hot.registered) == n_before - 1
    cleared_combo = DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    combos_now = {c for c, _cb in hot.registered.values()}
    assert cleared_combo not in combos_now


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


def test_end_drag_via_bus_submits_instead_of_dispatching(windows):
    """end_drag_via_bus is the hook-thread-safe variant — it queues the
    action onto the bus rather than calling the dispatcher synchronously.
    The window must NOT have moved until drain_actions runs."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)
    ctx.drag._throttle.reset()
    ctx.drag_poll()
    original = windows.windows[101]

    action = ctx.end_drag_via_bus()
    assert action is Action.LEFT_HALF
    # Window UNCHANGED — dispatch was queued, not run.
    assert windows.windows[101] == original
    assert ctx.bus.pending() == 1

    # Drain on the "Qt main thread" → now the window moves.
    ctx.drain_actions()
    assert windows.windows[101] == Rect(0, 0, 960, 1040)


def test_end_drag_via_bus_returns_none_when_no_zone(windows):
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    # No mouse updates → no hit.
    assert ctx.end_drag_via_bus() is None
    assert ctx.bus.pending() == 0


def test_make_drag_event_dispatcher_uses_bus_for_end(windows):
    """Verify that mouse-up through the dispatcher closure goes via the
    bus, not synchronously — required for hook-thread safety."""
    from windows_rectangle.adapters.win32_mousehook import (
        EVENT_LBUTTON_DOWN,
        EVENT_LBUTTON_UP,
        EVENT_MOVE,
    )
    from windows_rectangle.app import make_drag_event_dispatcher

    ctx = build(Settings(), windows)
    on_event, _detector = make_drag_event_dispatcher(ctx)

    # Click + drag to left edge + release.
    on_event(EVENT_LBUTTON_DOWN, 100, 100)
    on_event(EVENT_MOVE, 2, 540)  # crosses threshold + hit
    original = windows.windows[101]
    ctx.drag._throttle.reset()
    ctx.drag_poll()  # cache the hit
    on_event(EVENT_LBUTTON_UP, 2, 540)
    # Window untouched yet; action is queued.
    assert windows.windows[101] == original
    assert ctx.bus.pending() == 1


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
    ctx.drag_update(2, 540)  # left edge
    ctx.drag._throttle.reset()  # allow poll
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


def test_drain_drag_preview_hides_after_cursor_leaves_zone_mid_drag(windows):
    """Drag stays active, cursor was in a zone (overlay shown), then
    cursor moves to a non-zone area → on_hide must fire exactly once
    while the session is still active."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)  # left edge → hit
    ctx.drag._throttle.reset()
    shown: list = []
    hidden: list = []

    def go():
        return ctx.drain_drag_preview(
            on_show=lambda r: shown.append(r),
            on_hide=lambda: hidden.append(True),
        )

    assert go() is True  # overlay shown
    # Cursor moves to a non-zone area (mid-screen).
    ctx.drag_update(960, 540)
    ctx.drag._throttle.reset()
    assert go() is False
    assert hidden == [True]  # exactly one hide


def test_bind_hotkeys_via_bus_tolerates_failures(windows):
    """bind_hotkeys_via_bus must keep going when one register call raises."""
    hot = FakeHotkeys()
    ctx = build(Settings(), windows, hotkeys=hot)
    calls: list = []

    def register(combo, cb):
        calls.append(combo)
        if "ctrl+alt+left" in combo:
            raise RuntimeError("OS clash")
        return len(calls)

    bound = bind_hotkeys_via_bus(ctx, register)
    assert bound == len(DEFAULT_SHORTCUTS) - 1


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

    assert len(shown) == 1  # de-dup'd
    assert hidden == []


def test_drain_drag_preview_hides_once_after_being_shown(windows):
    """Show, then cursor leaves zone → exactly one on_hide fires; further
    idle ticks emit nothing."""
    ctx = build(Settings(), windows)
    ctx.begin_drag(Rect(100, 100, 800, 600))
    ctx.drag_update(2, 540)  # left edge → hit
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


def test_bind_mousehook_skips_install_when_drag_disabled(windows):
    """When drag_to_edge_enabled is False, bind_mousehook must short-
    circuit before importing Win32MouseHook — otherwise on a non-Windows
    host the import path would still succeed but instantiation later
    would raise, and OS-wide hook overhead is wasted when the feature
    is off."""
    from windows_rectangle.app import bind_mousehook

    ctx = build(Settings(drag_to_edge_enabled=False), windows)
    cleanup_before = len(list(ctx.cleanup))
    installed = bind_mousehook(ctx)
    assert installed is False
    # No cleanup handlers registered.
    assert len(list(ctx.cleanup)) == cleanup_before


def test_drag_event_dispatcher_routes_kinds(windows):
    """The on_event closure built by make_drag_event_dispatcher must
    route MOVE/LBUTTON_DOWN/LBUTTON_UP into the detector's state machine."""
    from windows_rectangle.adapters.win32_mousehook import (
        EVENT_LBUTTON_DOWN,
        EVENT_LBUTTON_UP,
        EVENT_MOVE,
    )
    from windows_rectangle.app import make_drag_event_dispatcher

    ctx = build(Settings(), windows)
    on_event, detector = make_drag_event_dispatcher(ctx)

    assert detector.state == "idle"
    on_event(EVENT_LBUTTON_DOWN, 100, 100)
    assert detector.state == "armed"
    on_event(EVENT_MOVE, 120, 120)  # past 5-px threshold
    assert detector.state == "dragging"
    on_event(EVENT_LBUTTON_UP, 120, 120)
    assert detector.state == "idle"


def test_drag_event_dispatcher_ignores_unknown_kinds(windows):
    """Right-button / middle-button / wheel events the snap pipeline
    doesn't care about must be silent no-ops, not raise."""
    from windows_rectangle.app import make_drag_event_dispatcher

    ctx = build(Settings(), windows)
    on_event, detector = make_drag_event_dispatcher(ctx)
    on_event("rbutton_down", 1, 1)
    on_event("scroll_up", 1, 1)
    assert detector.state == "idle"  # untouched


def test_subscribe_settings_fires_on_apply(windows):
    ctx = build(Settings(), windows)
    seen: list = []
    ctx.subscribe_settings(seen.append)
    ctx.apply_settings(Settings(gap=42))
    assert len(seen) == 1
    assert seen[0].gap == 42


def test_subscribe_settings_fires_after_state_is_wired(windows):
    """Subscribers must observe a fully-applied AppContext — not a
    half-mutated one — so e.g. the tooltip they paint matches dispatcher.gap."""
    ctx = build(Settings(gap=0), windows)

    seen_gap: list[int] = []

    def sub(_settings):
        # Reading dispatcher.gap (already mutated) at the time the
        # subscriber fires; must equal the new value.
        seen_gap.append(ctx.dispatcher.gap)

    ctx.subscribe_settings(sub)
    ctx.apply_settings(Settings(gap=15))
    assert seen_gap == [15]


def test_subscribe_settings_isolates_exceptions(windows):
    """A buggy subscriber must not poison the next subscriber, nor crash
    apply_settings."""
    ctx = build(Settings(), windows)
    a_called: list = []
    c_called: list = []

    def bad(_):
        raise RuntimeError("boom")

    ctx.subscribe_settings(a_called.append)
    ctx.subscribe_settings(bad)
    ctx.subscribe_settings(c_called.append)
    ctx.apply_settings(Settings(gap=7))
    assert len(a_called) == 1
    assert len(c_called) == 1


def test_maintenance_rate_limits_pruning(windows):
    """Two calls within prune_interval → second one is a noop and never
    walks the dicts."""
    ctx = build(Settings(), windows)
    # Stuff cycle + history with state.
    ctx.dispatcher.dispatch(Action.LEFT_HALF)
    calls: list = []
    ctx.dispatcher.prune_stale_state = lambda **_: (calls.append(True), 0)[1]  # type: ignore[method-assign]
    # First call at t=0 — runs.
    ctx.maintenance(now=0.0)
    # Second call at t=10s (< 60s interval default) — must be a noop.
    ctx.maintenance(now=10.0)
    assert len(calls) == 1
    # Third call after the interval — runs.
    ctx.maintenance(now=120.0)
    assert len(calls) == 2


def test_maintenance_tolerates_prune_exception(windows):
    """A racey IsWindow can raise — maintenance must swallow it so the
    Qt tick keeps running."""
    ctx = build(Settings(), windows)

    def boom(**_):
        raise OSError("racy IsWindow")

    ctx.dispatcher.prune_stale_state = boom  # type: ignore[method-assign]
    # No exception bubbles out.
    assert ctx.maintenance(now=1000.0) == 0


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
    build(
        Settings(launch_at_login=True), windows, autostart=a, autostart_command_line=r"C:\app.exe"
    )
    assert a.is_enabled()
    assert a.command_line == r"C:\app.exe"


def test_build_syncs_autostart_to_settings_false(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart

    a = MemoryAutoStart(enabled=True, command_line=r"C:\old.exe")
    build(
        Settings(launch_at_login=False), windows, autostart=a, autostart_command_line=r"C:\app.exe"
    )
    assert not a.is_enabled()


def test_apply_settings_toggles_autostart(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart

    a = MemoryAutoStart()
    ctx = build(
        Settings(launch_at_login=False), windows, autostart=a, autostart_command_line=r"C:\app.exe"
    )
    assert not a.is_enabled()
    ctx.apply_settings(Settings(launch_at_login=True))
    assert a.is_enabled()
    ctx.apply_settings(Settings(launch_at_login=False))
    assert not a.is_enabled()


def test_sync_autostart_noop_without_command_line(windows):
    from windows_rectangle.adapters.winreg_autostart import MemoryAutoStart

    a = MemoryAutoStart()
    # No command_line supplied → sync should do nothing.
    # build()'s sync_autostart fires as a side-effect; we assert via `a`.
    build(Settings(launch_at_login=True), windows, autostart=a)
    assert not a.is_enabled()


def test_autostart_failure_does_not_crash(windows):
    class BrokenAutoStart:
        def is_enabled(self):
            raise OSError("registry hosed")

        def enable(self, cl):
            raise OSError("nope")

        def disable(self):
            raise OSError("nope")

    # Should log + swallow — not raise.
    build(
        Settings(launch_at_login=True),
        windows,
        autostart=BrokenAutoStart(),
        autostart_command_line=r"C:\app.exe",
    )


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


def test_app_module_does_not_eagerly_import_win32_adapters():
    """Brief §4 / module docstring: adapters must be lazy-imported inside
    bind_win32/bind_mousehook. We can't reset sys.modules mid-session, so
    run the import in a fresh subprocess and inspect what got pulled in.
    This is the only way to make the assertion order-independent (other
    tests in this file call make_drag_event_dispatcher which lazy-imports
    win32_mousehook for EVENT_* constants, populating sys.modules)."""
    import subprocess
    import sys

    script = (
        "import sys\n"
        "import windows_rectangle.app\n"
        "bad = [n for n in sys.modules\n"
        "       if n.startswith('windows_rectangle.adapters.win32_')\n"
        "       or n == 'windows_rectangle.adapters.win_dpi'\n"
        "       or n == 'windows_rectangle.adapters.winreg_autostart']\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        },
    )
    bad = result.stdout.strip()
    assert bad == "", f"unexpectedly-loaded adapter modules: {bad}"
