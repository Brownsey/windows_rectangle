"""Native drag semantics with deterministic OS boundaries and real dispatch."""

from windows_rectangle.app import build, make_drag_event_dispatcher
from windows_rectangle.core.actions import Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings

from .conftest import FakeWindowManager, make_monitor


class DragWindows(FakeWindowManager):
    moving = None
    escape = False
    queries = 0
    escape_queries = 0

    def get_drag_window(self):
        self.queries += 1
        return self.moving

    def is_escape_pressed(self):
        self.escape_queries += 1
        return self.escape


def setup_drag():
    windows = DragWindows(
        monitors=[make_monitor(1, 0, 0, 1920, 1080), make_monitor(2, 1920, 0, 1920, 1080)],
        windows={101: Rect(100, 100, 800, 600), 102: Rect(300, 300, 500, 400)},
        active=101,
    )
    ctx = build(Settings(), windows)
    event, controller = make_drag_event_dispatcher(ctx)
    # Production start_mousehook owns the same consumer.
    ctx._mousehook = (object(), controller)
    return ctx, windows, event


def tick(ctx):
    ctx.drain_actions()


def start_move(ctx, windows, event):
    event("lbutton_down", 200, 110)
    windows.moving = 101
    tick(ctx)
    windows.windows[101] = Rect(120, 100, 800, 600)
    event("move", 220, 110)
    tick(ctx)


def test_content_drag_does_not_start_window_snap():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 200, 200)
    event("move", 2, 500)
    tick(ctx)
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []
    assert not ctx.drag.active


def test_completed_click_without_captured_window_stops_native_idle_queries():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 200, 200)
    event("lbutton_up", 200, 200)
    for _ in range(1000):
        tick(ctx)
    assert windows.queries == 0
    assert windows.escape_queries == 0
    assert not ctx.drag.active


def test_new_press_after_completed_click_can_start_native_drag():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 200, 200)
    event("lbutton_up", 200, 200)
    tick(ctx)
    event("lbutton_down", 200, 110)
    windows.moving = 101
    tick(ctx)
    assert ctx.drag.active


def test_hook_callback_never_queries_or_moves_windows():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 200, 110)
    for x in range(10000):
        event("move", x, 500)
    assert windows.queries == 0
    assert not ctx.drag.active
    assert windows.move_log == []


def test_release_keeps_captured_window_and_exact_destination_without_cycling():
    ctx, windows, event = setup_drag()
    # Prime shortcut cycling; drag must still produce a half, never a third.
    ctx.dispatcher.dispatch(Action.LEFT_HALF)
    windows.windows[101] = Rect(100, 100, 800, 600)
    windows.move_log.clear()
    start_move(ctx, windows, event)
    event("move", 2, 500)
    tick(ctx)
    windows.active = 102
    windows.moving = None
    event("lbutton_up", 3838, 500)
    tick(ctx)
    assert windows.move_log == [(101, Rect(2880, 0, 960, 1040))]
    assert windows.windows[102] == Rect(300, 300, 500, 400)


def test_resizing_does_not_snap():
    ctx, windows, event = setup_drag()
    start_move(ctx, windows, event)
    windows.windows[101] = Rect(120, 100, 900, 600)
    event("move", 2, 500)
    tick(ctx)
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []


def test_escape_cancels_preview_and_release():
    ctx, windows, event = setup_drag()
    start_move(ctx, windows, event)
    event("move", 2, 500)
    tick(ctx)
    windows.escape = True
    tick(ctx)
    windows.escape = False
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []
    assert not ctx.drag.active


def test_native_move_loop_ending_while_held_cancels_drag():
    ctx, windows, event = setup_drag()
    start_move(ctx, windows, event)
    event("move", 2, 500)
    tick(ctx)
    windows.moving = None
    tick(ctx)
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []


def test_native_move_can_begin_after_first_mouse_event():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 200, 110)
    event("move", 210, 110)
    tick(ctx)
    assert not ctx.drag.active
    windows.moving = 101
    tick(ctx)
    windows.windows[101] = Rect(120, 100, 800, 600)
    event("move", 2, 500)
    tick(ctx)
    event("lbutton_up", 2, 500)
    windows.moving = None
    tick(ctx)
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))]


def test_release_waits_until_windows_finishes_its_move_loop():
    ctx, windows, event = setup_drag()
    start_move(ctx, windows, event)
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []
    windows.moving = None
    tick(ctx)
    assert windows.move_log == [(101, Rect(0, 0, 960, 1040))]


def test_native_snap_on_release_does_not_cancel_our_exact_gapped_target():
    ctx, windows, event = setup_drag()
    ctx.apply_settings(Settings(gap=10))
    start_move(ctx, windows, event)
    # Windows can resize the moved window as its own edge-snap completes.
    windows.windows[101] = Rect(0, 0, 960, 1040)
    windows.moving = None
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == [(101, Rect(10, 10, 945, 1020))]


def test_resize_only_seen_on_release_is_not_mistaken_for_translation():
    ctx, windows, event = setup_drag()
    event("lbutton_down", 100, 100)
    windows.moving = 101
    tick(ctx)
    windows.windows[101] = Rect(2, 100, 898, 600)
    windows.moving = None
    event("lbutton_up", 2, 500)
    tick(ctx)
    assert windows.move_log == []
