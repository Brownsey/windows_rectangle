"""Real Qt event-loop checks for idle and cross-thread runtime scheduling."""

from __future__ import annotations

import threading
import time

import pytest

from windows_rectangle.app import AppContext, build, make_drag_event_dispatcher
from windows_rectangle.core.actions import Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings

from .conftest import FakeWindowManager, make_monitor


@pytest.fixture
def schedule():
    """Keep test timers alive, then stop them before the next Qt event loop."""
    qt_core = pytest.importorskip("PySide6.QtCore")
    timers = []

    def later(delay, callback):
        timer = qt_core.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timers.append(timer)
        timer.start(delay)
        return timer

    yield later
    for timer in timers:
        timer.stop()


def runtime(monkeypatch, windows=None):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt_core = pytest.importorskip("PySide6.QtCore")
    qt_widgets = pytest.importorskip("PySide6.QtWidgets")
    from windows_rectangle import __main__ as entry
    from windows_rectangle.ui import overlay, tray

    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    monkeypatch.setattr(tray, "install", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(overlay, "install", lambda: None)
    if windows is None:
        windows = FakeWindowManager(
            monitors=[make_monitor(1, 0, 0, 1920, 1080)],
            windows={101: Rect(100, 100, 800, 600)},
            active=101,
        )
    return qt_core, app, entry, build(Settings(shortcuts={}), windows), windows


def count_drains(monkeypatch, ctx):
    calls = []
    original = AppContext.drain_actions

    def counted(self):
        result = original(self)
        if self is ctx:
            calls.append(result)
        return result

    monkeypatch.setattr(AppContext, "drain_actions", counted)
    return calls


def test_qt_idle_has_no_repeating_16ms_drain(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    schedule(120, app.quit)
    assert entry._run_qt(ctx) == 0
    assert len(calls) <= 2


def test_qt_maintenance_runs_on_separate_deadline(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    maintenance = []
    original = AppContext.maintenance

    def counted(self, now=None):
        if self is ctx:
            maintenance.append(1)
        return original(self, now)

    monkeypatch.setattr(AppContext, "maintenance", counted)
    ctx.prune_interval = 0.03
    schedule(115, app.quit)
    assert entry._run_qt(ctx) == 0
    assert len(calls) <= 2
    assert len(maintenance) >= 3


def test_qt_drains_action_already_queued_at_startup(monkeypatch, schedule):
    qt_core, app, entry, ctx, windows = runtime(monkeypatch)
    ctx.bus.submit(Action.LEFT_HALF)
    calls = count_drains(monkeypatch, ctx)
    schedule(120, app.quit)
    assert entry._run_qt(ctx) == 0
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))]
    assert sum(calls) == 1


def test_qt_initial_drain_exception_retries_queued_action(monkeypatch, schedule):
    qt_core, app, entry, ctx, windows = runtime(monkeypatch)
    original = AppContext.drain_actions
    attempts = []

    def flaky(self):
        if self is ctx:
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("one failed drain")
        result = original(self)
        if self is ctx and windows.move_log:
            app.quit()
        return result

    monkeypatch.setattr(AppContext, "drain_actions", flaky)
    ctx.bus.submit(Action.LEFT_HALF)
    schedule(2000, app.quit)  # Bounded failure path; success quits on dispatch.
    assert entry._run_qt(ctx) == 0
    assert len(attempts) >= 2
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))]
    assert ctx.bus.pending() == 0


def test_qt_repeated_drain_exceptions_retry_on_timer_not_busy_loop(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    attempts = []

    def broken(self):
        if self is ctx:
            attempts.append(time.perf_counter())
            if len(attempts) == 3:
                app.quit()
            raise RuntimeError("still failing")

    monkeypatch.setattr(AppContext, "drain_actions", broken)
    monkeypatch.setattr(entry._log, "exception", lambda *_args, **_kwargs: None)
    ctx.bus.submit(Action.LEFT_HALF)
    schedule(2000, app.quit)  # Bounded failure path; success quits on third retry.
    assert entry._run_qt(ctx) == 0
    assert len(attempts) == 3
    assert all(b - a >= 0.005 for a, b in zip(attempts, attempts[1:], strict=False))
    assert ctx.bus.pending() == 1


def test_qt_cross_thread_action_wakes_and_dispatches_on_gui_thread(monkeypatch, schedule):
    qt_core, app, entry, ctx, windows = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    gui_thread = threading.get_ident()
    dispatch_threads = []
    original_set = FakeWindowManager.set_window_rect

    def recorded_set(self, handle, rect):
        dispatch_threads.append(threading.get_ident())
        return original_set(self, handle, rect)

    monkeypatch.setattr(FakeWindowManager, "set_window_rect", recorded_set)
    worker = threading.Thread(target=lambda: ctx.bus.submit(Action.LEFT_HALF))
    schedule(20, worker.start)
    schedule(350, app.quit)
    assert entry._run_qt(ctx) == 0
    worker.join(timeout=1)
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))], (ctx.bus.pending(), calls)
    assert dispatch_threads == [gui_thread]
    assert 1 <= len(calls) <= 3


def test_qt_burst_coalesces_wakes_and_drains_bounded_batches(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)

    def burst():
        for _ in range(40):
            ctx.bus.submit(Action.LEFT_HALF)

    schedule(5, lambda: threading.Thread(target=burst).start())
    schedule(500, app.quit)
    assert entry._run_qt(ctx) == 0
    assert sum(calls) == 40
    assert max(calls) <= 16
    assert len(calls) <= 5
    assert ctx.bus.pending() == 0


def test_qt_workspace_request_wakes_from_worker_thread(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    gui_thread = threading.get_ident()
    applied = []
    monkeypatch.setattr(
        AppContext,
        "apply_named_workspace",
        lambda self, workspace_id: applied.append((workspace_id, threading.get_ident())),
    )
    worker = threading.Thread(target=lambda: ctx.queue_workspace("saved"))
    schedule(20, worker.start)
    schedule(120, app.quit)
    assert entry._run_qt(ctx) == 0
    worker.join(timeout=1)
    assert applied == [("saved", gui_thread)]
    assert sum(calls) == 1
    assert len(calls) <= 3


class DragWindows(FakeWindowManager):
    moving = None
    escape = False

    def get_drag_window(self):
        return self.moving

    def is_escape_pressed(self):
        return self.escape


def drag_runtime(monkeypatch):
    windows = DragWindows(
        monitors=[make_monitor(1, 0, 0, 1920, 1080)],
        windows={101: Rect(100, 100, 800, 600)},
        active=101,
    )
    qt_core, app, entry, ctx, _ = runtime(monkeypatch, windows)
    event, controller = make_drag_event_dispatcher(ctx)

    class Hook:
        def shutdown(self):
            pass

    ctx._mousehook = (Hook(), controller)
    return qt_core, app, entry, ctx, windows, event


def test_qt_completed_click_stops_active_timer(monkeypatch, schedule):
    qt_core, app, entry, ctx, _, event = drag_runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    observed = {}

    def click():
        event("lbutton_down", 200, 200)
        event("lbutton_up", 200, 200)

    schedule(20, click)
    schedule(70, lambda: observed.update(early=len(calls)))
    schedule(130, lambda: observed.update(late=len(calls)))
    schedule(145, app.quit)
    assert entry._run_qt(ctx) == 0
    assert observed["early"] == observed["late"] == 1
    assert not ctx.has_pending_work()


def test_qt_polling_covers_late_move_and_captured_native_release(monkeypatch, schedule):
    qt_core, app, entry, ctx, windows, event = drag_runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)
    observed = {}
    schedule(20, lambda: event("lbutton_down", 200, 110))
    schedule(90, lambda: setattr(windows, "moving", 101))
    schedule(170, lambda: observed.update(late_move=ctx.drag.active))
    schedule(180, lambda: event("lbutton_up", 200, 110))
    schedule(240, lambda: observed.update(release_pending=ctx.has_pending_work()))
    schedule(250, lambda: setattr(windows, "moving", None))

    def mark_done():
        observed["done"] = len(calls)
        schedule(70, mark_stable)

    def mark_stable():
        observed["stable"] = len(calls)
        app.quit()

    schedule(320, mark_done)
    schedule(1000, app.quit)  # Guard a failed callback path.
    assert entry._run_qt(ctx) == 0
    assert observed["late_move"]
    assert observed["release_pending"]
    assert observed["done"] == observed["stable"]
    assert not ctx.has_pending_work()


def test_qt_facade_cancel_hides_preview_and_returns_idle(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    from windows_rectangle.ui import overlay

    controller = object()
    changes = []
    monkeypatch.setattr(overlay, "install", lambda: controller)
    monkeypatch.setattr(
        overlay, "show_for", lambda _controller, rect: changes.append(("show", rect))
    )
    monkeypatch.setattr(overlay, "hide", lambda _controller: changes.append(("hide", None)))
    calls = count_drains(monkeypatch, ctx)

    def begin():
        ctx.begin_drag(Rect(100, 100, 800, 600))
        ctx.drag_update(2, 500)

    schedule(20, begin)
    schedule(55, ctx.cancel_drag)
    schedule(100, app.quit)
    assert entry._run_qt(ctx) == 0
    assert [kind for kind, _ in changes] == ["show", "hide"]
    assert not ctx.has_pending_work()
    assert len(calls) <= 5


def test_qt_deferred_snap_wakes_dispatch_without_mouse_hook(monkeypatch, schedule):
    qt_core, app, entry, ctx, windows = runtime(monkeypatch)
    calls = count_drains(monkeypatch, ctx)

    def defer_snap():
        ctx.begin_drag(Rect(100, 100, 800, 600))
        ctx.drag_update(2, 500)
        ctx.end_drag_via_bus()

    schedule(20, defer_snap)
    schedule(150, app.quit)
    assert entry._run_qt(ctx) == 0
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))]
    assert sum(calls) == 1
    assert not ctx.has_pending_work()


def test_qt_teardown_removes_wake_callbacks(monkeypatch, schedule):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    schedule(20, app.quit)
    assert entry._run_qt(ctx) == 0
    assert ctx.bus.on_submit is None
    assert ctx.wake_ui is None
    assert ctx.bus.submit(Action.CENTER)


def test_qt_teardown_clears_callbacks_if_event_loop_raises(monkeypatch):
    _, app, entry, ctx, _ = runtime(monkeypatch)
    monkeypatch.setattr(
        type(app), "exec", lambda _self: (_ for _ in ()).throw(RuntimeError("quit"))
    )
    with pytest.raises(RuntimeError, match="quit"):
        entry._run_qt(ctx)
    assert ctx.bus.on_submit is None
    assert ctx.wake_ui is None


def test_qt_maintenance_schedules_from_last_actual_prune(monkeypatch):
    qt_core, app, entry, ctx, _ = runtime(monkeypatch)
    from windows_rectangle.app import AppContext
    from windows_rectangle.core.dispatcher import Dispatcher

    clock = type("Clock", (), {"now": 0.0})()
    prunes = []
    original_maintenance = AppContext.maintenance
    monkeypatch.setattr(
        AppContext,
        "maintenance",
        lambda self: original_maintenance(self, now=clock.now),
    )
    monkeypatch.setattr(
        Dispatcher,
        "prune_stale_state",
        lambda _self: prunes.append(clock.now) or 0,
    )

    class Signal:
        def connect(self, callback):
            self.callback = callback

    timers = []

    class Timer:
        def __init__(self):
            self.timeout = Signal()
            self.interval = 0
            self.single_shot = False
            self.active = False
            timers.append(self)

        def setTimerType(self, _kind):
            pass

        def setSingleShot(self, value):
            self.single_shot = value

        def setInterval(self, interval):
            self.interval = interval

        def start(self):
            self.active = True
            self.due = clock.now + self.interval / 1000

        def stop(self):
            self.active = False

        def isActive(self):
            return self.active

    def run_callbacks(_self):
        maintenance_timer = next(timer for timer in timers if timer.interval == 60000)
        for lateness in (0.010, 0.005):
            clock.now = maintenance_timer.due + lateness
            if maintenance_timer.single_shot:
                maintenance_timer.active = False
            else:
                maintenance_timer.due += maintenance_timer.interval / 1000
            maintenance_timer.timeout.callback()
        return 0

    monkeypatch.setattr(qt_core, "QTimer", Timer)
    monkeypatch.setattr(type(app), "exec", run_callbacks)
    assert entry._run_qt(ctx) == 0
    assert len(prunes) == 3  # Startup and both actual 60 s intervals.
