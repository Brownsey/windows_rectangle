"""Tests for windows_rectangle.core.monitors."""

from windows_rectangle.core.geometry import Rect

from windows_rectangle.core import monitors

from .conftest import make_monitor

M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)
M2 = make_monitor(2, 1920, 0, 1920, 1080)
M3 = make_monitor(3, -1920, 100, 1920, 1080)


def test_ordered_left_to_right():
    ordered = monitors.ordered([M2, M3, M1])
    assert [m.handle for m in ordered] == [3, 1, 2]


def test_neighbor_next_wraps():
    seq = [M1, M2, M3]
    assert monitors.neighbor(seq, M1, direction=1).handle == M2.handle  # M3 sorts before M1
    # After ordering: M3, M1, M2. Next of M2 wraps to M3.
    assert monitors.neighbor(seq, M2, direction=1).handle == M3.handle


def test_neighbor_prev_wraps():
    seq = [M1, M2, M3]
    # Ordered: M3, M1, M2. Prev of M3 wraps to M2.
    assert monitors.neighbor(seq, M3, direction=-1).handle == M2.handle


def test_neighbor_single_monitor_returns_same():
    assert monitors.neighbor([M1], M1, direction=1).handle == M1.handle
    assert monitors.neighbor([M1], M1, direction=-1).handle == M1.handle


def test_neighbor_rejects_zero_direction():
    import pytest

    with pytest.raises(ValueError):
        monitors.neighbor([M1, M2], M1, direction=0)


def test_neighbor_empty_monitors_returns_current():
    """Defensive: empty list should never crash — return the current
    monitor unchanged so the caller can no-op."""
    assert monitors.neighbor([], M1, direction=1).handle == M1.handle


def test_index_of_returns_ordered_position():
    # Ordered: M3 (x=-1920), M1 (x=0), M2 (x=1920).
    assert monitors.index_of([M2, M3, M1], M3) == 0
    assert monitors.index_of([M2, M3, M1], M1) == 1
    assert monitors.index_of([M2, M3, M1], M2) == 2


def test_index_of_returns_zero_when_not_found():
    """index_of falls back to 0 for an unknown monitor — used as a
    safe-default for neighbor() when the live foreground monitor has
    just been hot-unplugged between detection and lookup."""
    unknown = make_monitor(99, 5000, 5000, 1000, 1000)
    assert monitors.index_of([M1, M2], unknown) == 0


def test_move_to_monitor_preserves_relative_fraction():
    # A right-half of M1's work area...
    win = Rect(960, 0, 960, 1040)
    out = monitors.move_to_monitor(win, M1, M2)
    # ...should become the right-half of M2's work area.
    assert out == Rect(1920 + 960, 0, 960, 1040)


def test_move_to_monitor_same_monitor_no_op():
    win = Rect(100, 100, 800, 600)
    assert monitors.move_to_monitor(win, M1, M1) == win


def test_best_monitor_for_window_picks_largest_overlap():
    # Window mostly on M2, slightly on M1.
    win = Rect(1800, 100, 800, 600)
    assert monitors.best_monitor_for(win, [M1, M2]).handle == M2.handle


def test_best_monitor_for_window_handles_empty():
    assert monitors.best_monitor_for(Rect(0, 0, 100, 100), []) is None
