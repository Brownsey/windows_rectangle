"""Tests for windows_rectangle.core.dispatcher."""

import pytest
from windows_rectangle.core.actions import Action
from windows_rectangle.core.cycle import CycleState
from windows_rectangle.core.dispatcher import Dispatcher
from windows_rectangle.core.eligibility import WindowFlags
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.history import History

from .conftest import FakeWindowManager, make_monitor

M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)
M2 = make_monitor(2, 1920, 0, 1920, 1080)


# ----- Fixtures -------------------------------------------------------


@pytest.fixture
def fake_wm() -> FakeWindowManager:
    wm = FakeWindowManager(monitors=[M1, M2])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    return wm


@pytest.fixture
def dispatcher(fake_wm: FakeWindowManager) -> Dispatcher:
    return Dispatcher(fake_wm)


# ----- Geometry actions -----------------------------------------------


def test_left_half_moves_window(dispatcher, fake_wm):
    result = dispatcher.dispatch(Action.LEFT_HALF)
    assert result.moved
    assert result.reason == "ok"
    # M1 work area is 1920x1040 (40px taskbar); left half = (0,0,960,1040).
    assert fake_wm.windows[101] == Rect(0, 0, 960, 1040)


def test_no_active_window_returns_ok_status(fake_wm, dispatcher):
    fake_wm.active = None
    result = dispatcher.dispatch(Action.LEFT_HALF)
    assert not result.moved
    assert result.reason == "no_active_window"


def test_blocked_window_returns_blocked_and_drops_undo(fake_wm, dispatcher):
    fake_wm.blocked.add(101)
    result = dispatcher.dispatch(Action.LEFT_HALF)
    assert not result.moved
    assert result.reason == "blocked"
    # And nothing got pushed to history.
    restored = dispatcher.dispatch(Action.RESTORE)
    assert restored.reason == "no_undo"


def test_gap_setting_applies(fake_wm):
    d = Dispatcher(fake_wm, gap=10)
    d.dispatch(Action.LEFT_HALF)
    # Left half with gap=10 → x=10, width = 950 (960 - 10 outer - 5 inner)
    r = fake_wm.windows[101]
    assert r.left == 10  # outer gap on left edge
    assert r.right == 955  # 960 - 5 (half inner gutter)


def test_gap_setter_clamps_negative(fake_wm):
    d = Dispatcher(fake_wm)
    d.gap = -5
    assert d.gap == 0


# ----- Cycling --------------------------------------------------------


def test_repeat_left_half_cycles(fake_wm):
    cycle = CycleState(idle_timeout=10)
    d = Dispatcher(fake_wm, cycle=cycle)
    d.dispatch(Action.LEFT_HALF)
    assert fake_wm.windows[101] == Rect(0, 0, 960, 1040)
    d.dispatch(Action.LEFT_HALF)
    # First third = 1920/3 ≈ 640
    assert fake_wm.windows[101].width == 640
    d.dispatch(Action.LEFT_HALF)
    # First two-thirds = 2*1920/3 = 1280
    assert fake_wm.windows[101].width == 1280


# ----- Undo (RESTORE) ------------------------------------------------


def test_restore_undoes_last_move(fake_wm, dispatcher):
    original = fake_wm.windows[101]
    dispatcher.dispatch(Action.LEFT_HALF)
    assert fake_wm.windows[101] != original
    restored = dispatcher.dispatch(Action.RESTORE)
    assert restored.moved
    assert fake_wm.windows[101] == original


def test_restore_with_no_history_is_noop(fake_wm, dispatcher):
    result = dispatcher.dispatch(Action.RESTORE)
    assert not result.moved
    assert result.reason == "no_undo"


def test_restore_consumes_one_at_a_time(fake_wm):
    h = History()
    d = Dispatcher(fake_wm, history=h)
    original = fake_wm.windows[101]
    d.dispatch(Action.LEFT_HALF)
    after_left = fake_wm.windows[101]
    d.dispatch(Action.RIGHT_HALF)
    # Undo back to after_left.
    d.dispatch(Action.RESTORE)
    assert fake_wm.windows[101] == after_left
    # Undo back to original.
    d.dispatch(Action.RESTORE)
    assert fake_wm.windows[101] == original


# ----- Multi-monitor -------------------------------------------------


def test_next_display_moves_to_neighbor(fake_wm, dispatcher):
    result = dispatcher.dispatch(Action.NEXT_DISPLAY)
    assert result.moved
    # Window was on M1 (x=0..1920). After move it should be on M2 (x=1920..3840).
    r = fake_wm.windows[101]
    assert r.x >= 1920
    assert r.right <= 3840


def test_next_display_preserves_relative_position(fake_wm):
    fake_wm.windows[101] = Rect(960, 0, 960, 1040)  # right half of M1's work area
    d = Dispatcher(fake_wm)
    d.dispatch(Action.NEXT_DISPLAY)
    r = fake_wm.windows[101]
    # Should now be right half of M2's work area.
    assert r == Rect(1920 + 960, 0, 960, 1040)


def test_next_display_single_monitor_no_op(fake_wm):
    fake_wm.monitors = [M1]
    d = Dispatcher(fake_wm)
    before = fake_wm.windows[101]
    result = d.dispatch(Action.NEXT_DISPLAY)
    assert not result.moved
    assert result.reason == "single_monitor"
    assert fake_wm.windows[101] == before


def test_prev_display_wraps(fake_wm):
    d = Dispatcher(fake_wm)
    # Window on M1; prev should wrap to M2.
    d.dispatch(Action.PREV_DISPLAY)
    r = fake_wm.windows[101]
    assert r.x >= 1920


def test_direct_display_moves_to_requested_monitor(fake_wm, dispatcher):
    result = dispatcher.dispatch(Action.DISPLAY_2)
    assert result.moved
    assert fake_wm.windows[101].x >= M2.work_area.x


def test_direct_display_reports_missing_monitor(fake_wm, dispatcher):
    result = dispatcher.dispatch(Action.DISPLAY_3)
    assert not result.moved
    assert result.reason == "display_unavailable"


def test_direct_display_on_current_monitor_is_no_change(fake_wm, dispatcher):
    result = dispatcher.dispatch(Action.DISPLAY_1)
    assert not result.moved
    assert result.reason == "no_change"


def test_toggle_always_on_top_enables_and_disables(fake_wm, dispatcher):
    enabled = dispatcher.dispatch(Action.TOGGLE_ALWAYS_ON_TOP)
    assert enabled.moved
    assert enabled.after == enabled.before
    assert 101 in fake_wm.always_on_top

    disabled = dispatcher.dispatch(Action.TOGGLE_ALWAYS_ON_TOP)
    assert disabled.moved
    assert 101 not in fake_wm.always_on_top


def test_toggle_always_on_top_reports_blocked(fake_wm, dispatcher):
    fake_wm.blocked_topmost.add(101)
    result = dispatcher.dispatch(Action.TOGGLE_ALWAYS_ON_TOP)
    assert not result.moved
    assert result.reason == "blocked"


# ----- Prune stale state --------------------------------------------


def test_prune_stale_drops_closed_window_state(fake_wm):
    d = Dispatcher(fake_wm)
    d.dispatch(Action.LEFT_HALF)  # populates history + cycle for 101
    # Simulate window 101 closing.
    del fake_wm.windows[101]
    fake_wm.active = None
    dropped = d.prune_stale_state()
    assert dropped >= 1


def test_prune_stale_state_memoizes_across_cycle_and_history(fake_wm):
    """A HWND with both cycle + history entries should only be checked
    once by is_alive when prune_stale_state runs the cross-structure sweep."""
    d = Dispatcher(fake_wm)
    d.dispatch(Action.LEFT_HALF)  # writes both cycle + history for 101

    calls: list = []

    def is_alive(wid):
        calls.append(wid)
        return False

    d.prune_stale_state(is_alive=is_alive)
    # Exactly one call for window 101 despite it being in both data structures.
    assert calls == [101]


# ----- Maximized/snapped pre-restore (brief §5 #4) -----------------


def test_maximized_window_is_restored_before_move(fake_wm, dispatcher):
    fake_wm.maximized.add(101)
    dispatcher.dispatch(Action.LEFT_HALF)
    # The pre-restore call happened, and the window is at left-half.
    assert fake_wm.restore_log == [101]
    assert 101 not in fake_wm.maximized
    assert fake_wm.windows[101] == Rect(0, 0, 960, 1040)


def test_non_maximized_window_skips_restore(fake_wm, dispatcher):
    dispatcher.dispatch(Action.LEFT_HALF)
    assert fake_wm.restore_log == []


def test_restore_action_does_not_trigger_pre_restore(fake_wm, dispatcher):
    # First push something into history so RESTORE has work to do.
    dispatcher.dispatch(Action.LEFT_HALF)
    fake_wm.maximized.add(101)
    fake_wm.restore_log.clear()
    dispatcher.dispatch(Action.RESTORE)
    # RESTORE bypasses _move's pre-restore logic.
    assert fake_wm.restore_log == []


# ----- Eligibility (brief §5 #10) -----------------------------------


def test_ineligible_window_is_skipped(fake_wm, dispatcher):
    # Tool window (no caption either) → Capability.NONE
    fake_wm.flags[101] = WindowFlags(is_tool_window=True)
    result = dispatcher.dispatch(Action.LEFT_HALF)
    assert not result.moved
    assert result.reason == "ineligible"
    # Nothing should have been moved.
    assert fake_wm.move_log == []


def test_move_only_window_keeps_size_centered_at_target(fake_wm, dispatcher):
    # Fixed-size dialog: caption present, no thick frame -> Capability.MOVE only.
    fake_wm.windows[101] = Rect(100, 100, 400, 300)
    fake_wm.flags[101] = WindowFlags(has_caption=True, has_thick_frame=False)
    dispatcher.dispatch(Action.LEFT_HALF)
    r = fake_wm.windows[101]
    # Size preserved.
    assert r.width == 400 and r.height == 300
    # Center sits at the left-half's center: x=480 (960/2), y=520 (1040/2).
    assert abs(r.center_x - 480) <= 1
    assert abs(r.center_y - 520) <= 1


def test_move_only_window_clamped_to_work_area(fake_wm, dispatcher):
    # A move-only window wider than the work-area's half would otherwise spill.
    fake_wm.windows[101] = Rect(0, 0, 1500, 1000)  # huge
    fake_wm.flags[101] = WindowFlags(has_caption=True, has_thick_frame=False)
    dispatcher.dispatch(Action.LEFT_HALF)
    r = fake_wm.windows[101]
    # Must stay inside work area.
    assert r.left >= 0 and r.top >= 0
    assert r.right <= 1920 and r.bottom <= 1040


class _NoMonitorWM(FakeWindowManager):
    """FakeWindowManager that always reports 'no monitor' — simulates a
    racy hot-unplug or a window dragged completely offscreen."""

    def monitor_for_window(self, handle):
        return None


def test_apply_geometry_no_monitor_returns_no_monitor():
    """If the WindowManager can't tell us which monitor the window is on
    (e.g. window dragged offscreen mid-call), dispatch bails cleanly."""
    wm = _NoMonitorWM(monitors=[M1, M2])
    wm.windows[202] = Rect(0, 0, 500, 400)
    wm.active = 202
    d = Dispatcher(wm)
    result = d.dispatch(Action.LEFT_HALF)
    assert not result.moved
    assert result.reason == "no_monitor"


def test_next_display_no_monitor_returns_no_monitor():
    """Same guard in the multi-display path."""
    wm = _NoMonitorWM(monitors=[M1, M2])
    wm.windows[202] = Rect(0, 0, 500, 400)
    wm.active = 202
    d = Dispatcher(wm)
    result = d.dispatch(Action.NEXT_DISPLAY)
    assert not result.moved
    assert result.reason == "no_monitor"


def test_no_change_when_target_equals_before(fake_wm):
    """If the computed target rect is identical to current, we record
    'no_change' rather than going through a redundant SetWindowPos."""
    fake_wm.windows[101] = Rect(0, 0, 960, 1040)  # already at left-half geometry
    d = Dispatcher(fake_wm, gap=0)
    result = d.dispatch(Action.LEFT_HALF)
    assert not result.moved
    assert result.reason == "no_change"


def test_dispatcher_default_almost_maximize_scale_uses_module_constant(fake_wm):
    """When Dispatcher.almost_maximize_scale is left as None (tests that
    don't go through build()), the ALMOST_MAXIMIZE dispatch falls back
    to the module ALMOST_MAXIMIZE_SCALE = 0.85 — matching pre-iter-60
    behaviour so no test that doesn't care about scale gets broken."""
    d = Dispatcher(fake_wm)
    assert d.almost_maximize_scale is None  # default, not threaded from Settings
    d.dispatch(Action.ALMOST_MAXIMIZE)
    r = fake_wm.windows[101]
    # 1920 × 1040 work area × 0.85 = 1632 × 884.
    assert r.width == int(1920 * 0.85)
    assert r.height == int(1040 * 0.85)
