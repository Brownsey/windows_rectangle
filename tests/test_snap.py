"""Tests for windows_rectangle.core.snap."""

from windows_rectangle.core.actions import Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.snap import (
    CORNER_SIZE,
    EDGE_THICKNESS,
    SnapZone,
    find_snap,
    zone_at,
)

from .conftest import make_monitor


M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)
M2 = make_monitor(2, 1920, 0, 1920, 1080)


def test_center_returns_none():
    assert zone_at(960, 540, M1) is SnapZone.NONE


def test_left_edge_detected():
    assert zone_at(2, 540, M1) is SnapZone.LEFT


def test_right_edge_detected():
    # Right edge — within EDGE_THICKNESS of bounds.right
    assert zone_at(1920 - 1, 540, M1) is SnapZone.RIGHT


def test_top_edge_detected():
    assert zone_at(960, 1, M1) is SnapZone.TOP


def test_bottom_edge_detected():
    assert zone_at(960, 1080 - 1, M1) is SnapZone.BOTTOM


def test_corner_wins_over_edges():
    # Cursor near (0,0) — well inside CORNER_SIZE on both axes.
    assert zone_at(5, 5, M1) is SnapZone.TOP_LEFT
    assert zone_at(1920 - 5, 5, M1) is SnapZone.TOP_RIGHT
    assert zone_at(5, 1080 - 5, M1) is SnapZone.BOTTOM_LEFT
    assert zone_at(1920 - 5, 1080 - 5, M1) is SnapZone.BOTTOM_RIGHT


def test_corner_requires_being_on_an_edge_band():
    # Inside corner box (< CORNER_SIZE from both corners) but outside EDGE_THICKNESS
    # band on every side → no snap. Avoids "kinda-near-the-corner" false positives.
    assert zone_at(CORNER_SIZE - 1, CORNER_SIZE - 1, M1) is SnapZone.NONE
    # Same point but with one axis pushed inside the edge band → corner triggers.
    assert zone_at(EDGE_THICKNESS - 1, CORNER_SIZE - 1, M1) is SnapZone.TOP_LEFT


def test_outside_monitor_returns_none():
    assert zone_at(-10, 540, M1) is SnapZone.NONE
    assert zone_at(960, -10, M1) is SnapZone.NONE


def test_find_snap_picks_right_monitor():
    # Cursor on M2's left edge.
    hit = find_snap(1920 + 2, 500, [M1, M2])
    assert hit.zone is SnapZone.LEFT
    assert hit.monitor.handle == M2.handle
    assert hit.action is Action.LEFT_HALF
    assert hit.target == Rect(1920, 0, 960, 1040)  # M2 left half of work area


def test_find_snap_top_zone_maps_to_maximize():
    hit = find_snap(960, 1, [M1])
    assert hit.action is Action.MAXIMIZE
    assert hit.target == M1.work_area


def test_find_snap_returns_none_in_center():
    hit = find_snap(960, 540, [M1, M2])
    assert hit.zone is SnapZone.NONE
    assert hit.action is None
    assert hit.target is None


def test_find_snap_empty_monitors():
    hit = find_snap(0, 0, [])
    assert hit.zone is SnapZone.NONE


def test_edge_thickness_param_respected():
    # Cursor at x=15: inside default EDGE_THICKNESS (24), but outside custom edge=10.
    assert zone_at(15, 540, M1, edge=10) is SnapZone.NONE
    assert zone_at(15, 540, M1, edge=EDGE_THICKNESS) is SnapZone.LEFT


def test_find_snap_includes_gap_in_preview():
    hit = find_snap(2, 540, [M1], gap=10)
    # Left half with gap=10: outer x=10, width=945
    assert hit.target.left == 10
    assert hit.target.right == 955
