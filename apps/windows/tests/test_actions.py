"""Tests for windows_rectangle.core.actions."""

import pytest
from windows_rectangle.core.actions import (
    DEFAULT_SHORTCUTS,
    Action,
    apply,
    is_geometry_action,
)
from windows_rectangle.core.geometry import Rect

WORK = Rect(0, 0, 1920, 1080)
WIN = Rect(100, 100, 800, 600)


# ----- Halves ---------------------------------------------------------


def test_left_half():
    r = apply(Action.LEFT_HALF, WIN, WORK)
    assert r == Rect(0, 0, 960, 1080)


def test_right_half():
    r = apply(Action.RIGHT_HALF, WIN, WORK)
    assert r == Rect(960, 0, 960, 1080)


def test_top_half():
    r = apply(Action.TOP_HALF, WIN, WORK)
    assert r == Rect(0, 0, 1920, 540)


def test_bottom_half():
    r = apply(Action.BOTTOM_HALF, WIN, WORK)
    assert r == Rect(0, 540, 1920, 540)


def test_halves_partition_work_area_without_gap():
    a = apply(Action.LEFT_HALF, WIN, WORK)
    b = apply(Action.RIGHT_HALF, WIN, WORK)
    assert a.right == b.left and a.left == 0 and b.right == 1920


# ----- Quarters -------------------------------------------------------


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.TOP_LEFT_QUARTER, Rect(0, 0, 960, 540)),
        (Action.TOP_RIGHT_QUARTER, Rect(960, 0, 960, 540)),
        (Action.BOTTOM_LEFT_QUARTER, Rect(0, 540, 960, 540)),
        (Action.BOTTOM_RIGHT_QUARTER, Rect(960, 540, 960, 540)),
    ],
)
def test_quarters(action, expected):
    assert apply(action, WIN, WORK) == expected


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.TOP_LEFT_SIXTH, Rect(0, 0, 640, 540)),
        (Action.TOP_RIGHT_SIXTH, Rect(1280, 0, 640, 540)),
        (Action.BOTTOM_LEFT_SIXTH, Rect(0, 540, 640, 540)),
        (Action.BOTTOM_RIGHT_SIXTH, Rect(1280, 540, 640, 540)),
    ],
)
def test_corner_sixths(action, expected):
    assert apply(action, WIN, WORK) == expected


def test_center_sixths_complete_the_three_by_two_grid():
    assert apply(Action.TOP_CENTER_SIXTH, WIN, WORK) == Rect(640, 0, 640, 540)
    assert apply(Action.BOTTOM_CENTER_SIXTH, WIN, WORK) == Rect(640, 540, 640, 540)


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.TOP_LEFT_THIRD, Rect(0, 0, 1280, 540)),
        (Action.TOP_RIGHT_THIRD, Rect(640, 0, 1280, 540)),
        (Action.BOTTOM_LEFT_THIRD, Rect(0, 540, 1280, 540)),
        (Action.BOTTOM_RIGHT_THIRD, Rect(640, 540, 1280, 540)),
        (Action.TOP_VERTICAL_THIRD, Rect(0, 0, 1920, 360)),
        (Action.MIDDLE_VERTICAL_THIRD, Rect(0, 360, 1920, 360)),
        (Action.BOTTOM_VERTICAL_THIRD, Rect(0, 720, 1920, 360)),
        (Action.TOP_VERTICAL_TWO_THIRDS, Rect(0, 0, 1920, 720)),
        (Action.BOTTOM_VERTICAL_TWO_THIRDS, Rect(0, 360, 1920, 720)),
    ],
)
def test_dense_thirds(action, expected):
    assert apply(action, WIN, WORK) == expected


def test_quadrant_thirds_are_orientation_aware():
    portrait = Rect(0, 0, 900, 1600)
    assert apply(Action.TOP_RIGHT_THIRD, WIN, portrait) == Rect(450, 0, 450, 1067)
    assert apply(Action.BOTTOM_LEFT_THIRD, WIN, portrait) == Rect(0, 533, 450, 1067)


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.FIRST_FOURTH, Rect(0, 0, 480, 1080)),
        (Action.SECOND_FOURTH, Rect(480, 0, 480, 1080)),
        (Action.THIRD_FOURTH, Rect(960, 0, 480, 1080)),
        (Action.LAST_FOURTH, Rect(1440, 0, 480, 1080)),
        (Action.CENTER_HALF, Rect(480, 0, 960, 1080)),
        (Action.CENTER_TWO_THIRDS, Rect(320, 0, 1280, 1080)),
        (Action.FIRST_THREE_FOURTHS, Rect(0, 0, 1440, 1080)),
        (Action.CENTER_THREE_FOURTHS, Rect(240, 0, 1440, 1080)),
        (Action.LAST_THREE_FOURTHS, Rect(480, 0, 1440, 1080)),
    ],
)
def test_oriented_bands_on_landscape(action, expected):
    assert apply(action, WIN, WORK) == expected


def test_oriented_bands_rotate_on_portrait_display():
    portrait = Rect(-200, 50, 900, 1600)
    assert apply(Action.FIRST_FOURTH, WIN, portrait) == Rect(-200, 50, 900, 400)
    assert apply(Action.CENTER_HALF, WIN, portrait) == Rect(-200, 450, 900, 800)


def test_oriented_band_gap_has_outer_and_inner_gutters():
    assert apply(Action.SECOND_FOURTH, WIN, WORK, gap=10) == Rect(485, 10, 470, 1060)


# ----- Thirds ---------------------------------------------------------


def test_thirds_tile_work_area_exactly():
    a = apply(Action.FIRST_THIRD, WIN, WORK)
    b = apply(Action.CENTER_THIRD, WIN, WORK)
    c = apply(Action.LAST_THIRD, WIN, WORK)
    assert a.left == 0
    assert a.right == b.left
    assert b.right == c.left
    assert c.right == 1920


def test_two_thirds():
    assert apply(Action.FIRST_TWO_THIRDS, WIN, WORK) == Rect(0, 0, 1280, 1080)
    assert apply(Action.LAST_TWO_THIRDS, WIN, WORK) == Rect(640, 0, 1280, 1080)


# ----- Maximize / center / scale -------------------------------------


def test_maximize_fills_work_area():
    assert apply(Action.MAXIMIZE, WIN, WORK) == WORK


def test_maximize_height_keeps_horizontal_position():
    r = apply(Action.MAXIMIZE_HEIGHT, WIN, WORK)
    assert r.x == WIN.x
    assert r.width == WIN.width
    assert r.y == WORK.y
    assert r.height == WORK.height


def test_maximize_width_keeps_vertical_position():
    r = apply(Action.MAXIMIZE_WIDTH, WIN, WORK)
    assert r == Rect(0, WIN.y, WORK.width, WIN.height)


def test_maximize_width_applies_horizontal_gap_only():
    assert apply(Action.MAXIMIZE_WIDTH, WIN, WORK, gap=10) == Rect(
        10, WIN.y, WORK.width - 20, WIN.height
    )


def test_maximize_height_applies_top_bottom_gap():
    r = apply(Action.MAXIMIZE_HEIGHT, WIN, WORK, gap=10)
    # With gap > 0, top + bottom should inset; x/width still untouched.
    assert r.x == WIN.x
    assert r.width == WIN.width
    assert r.y == WORK.y + 10
    assert r.height == WORK.height - 20


def test_almost_maximize_uses_default_scale():
    """Without an override, almost_maximize uses the module-level
    ALMOST_MAXIMIZE_SCALE (0.85)."""
    r = apply(Action.ALMOST_MAXIMIZE, WIN, WORK)
    assert r.width == int(WORK.width * 0.85)
    assert r.height == int(WORK.height * 0.85)


def test_almost_maximize_honours_scale_override():
    """When apply() is given almost_maximize_scale, it overrides the
    module-level default — closes the brief-§2-#7 prefs-slider gap."""
    r = apply(Action.ALMOST_MAXIMIZE, WIN, WORK, almost_maximize_scale=0.5)
    assert r.width == int(WORK.width * 0.5)
    assert r.height == int(WORK.height * 0.5)


def test_almost_maximize_scale_ignored_for_other_actions():
    """Other geometry actions don't read almost_maximize_scale."""
    r = apply(Action.LEFT_HALF, WIN, WORK, almost_maximize_scale=0.5)
    # Left half of 1920×1040 = 960×1040 at origin.
    assert r.width == 960
    assert r.x == 0


def test_almost_maximize_centered_and_smaller():
    r = apply(Action.ALMOST_MAXIMIZE, WIN, WORK)
    assert r.width < WORK.width
    assert r.height < WORK.height
    assert abs(r.center_x - WORK.center_x) <= 1
    assert abs(r.center_y - WORK.center_y) <= 1


def test_center_doesnt_resize():
    r = apply(Action.CENTER, WIN, WORK)
    assert (r.width, r.height) == (WIN.width, WIN.height)
    assert abs(r.center_x - WORK.center_x) <= 1


def test_center_prominently_uses_upper_visual_quarter():
    assert apply(Action.CENTER_PROMINENTLY, WIN, WORK) == Rect(560, 120, 800, 600)


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.MOVE_LEFT, Rect(0, 240, 800, 600)),
        (Action.MOVE_RIGHT, Rect(1120, 240, 800, 600)),
        (Action.MOVE_UP, Rect(560, 0, 800, 600)),
        (Action.MOVE_DOWN, Rect(560, 480, 800, 600)),
    ],
)
def test_move_actions_preserve_size_and_center_other_axis(action, expected):
    assert apply(action, WIN, WORK) == expected


@pytest.mark.parametrize(
    "action, expected_size",
    [
        (Action.LARGER_WIDTH, (830, 600)),
        (Action.SMALLER_WIDTH, (770, 600)),
        (Action.LARGER_HEIGHT, (800, 630)),
        (Action.SMALLER_HEIGHT, (800, 570)),
    ],
)
def test_dimension_only_resize_keeps_center(action, expected_size):
    result = apply(action, WIN, WORK)
    assert (result.width, result.height) == expected_size
    assert (result.center_x, result.center_y) == (WIN.center_x, WIN.center_y)


@pytest.mark.parametrize(
    "action, expected",
    [
        (Action.HALVE_WIDTH_LEFT, Rect(100, 100, 400, 600)),
        (Action.HALVE_WIDTH_RIGHT, Rect(500, 100, 400, 600)),
        (Action.DOUBLE_WIDTH_LEFT, Rect(0, 100, 900, 600)),
        (Action.DOUBLE_WIDTH_RIGHT, Rect(100, 100, 1600, 600)),
        (Action.HALVE_HEIGHT_UP, Rect(100, 100, 800, 300)),
        (Action.HALVE_HEIGHT_DOWN, Rect(100, 400, 800, 300)),
        (Action.DOUBLE_HEIGHT_UP, Rect(100, 0, 800, 700)),
        (Action.DOUBLE_HEIGHT_DOWN, Rect(100, 100, 800, 980)),
    ],
)
def test_anchored_dimension_scaling(action, expected):
    assert apply(action, WIN, WORK) == expected


def test_larger_grows_keeps_center():
    r = apply(Action.LARGER, WIN, WORK)
    assert r.width > WIN.width
    assert r.height > WIN.height
    assert abs(r.center_x - WIN.center_x) <= 1


def test_smaller_shrinks_keeps_center():
    r = apply(Action.SMALLER, WIN, WORK)
    assert r.width < WIN.width
    assert r.height < WIN.height
    assert abs(r.center_x - WIN.center_x) <= 1


def test_smaller_respects_minimum():
    tiny = Rect(0, 0, 100, 80)
    r = apply(Action.SMALLER, tiny, WORK)
    # MIN_WINDOW_W=80, MIN_WINDOW_H=60 → can't go below those
    assert r.width >= 80
    assert r.height >= 60


def test_larger_caps_to_work_area():
    huge = Rect(0, 0, 1900, 1070)
    r = apply(Action.LARGER, huge, WORK)
    assert r.width <= WORK.width
    assert r.height <= WORK.height


# ----- Gap behaviour --------------------------------------------------


def test_left_half_with_gap_leaves_gutter():
    a = apply(Action.LEFT_HALF, WIN, WORK, gap=10)
    b = apply(Action.RIGHT_HALF, WIN, WORK, gap=10)
    assert b.left - a.right == 10
    assert a.left == 10  # outer gap


def test_maximize_with_gap_insets_all_sides():
    r = apply(Action.MAXIMIZE, WIN, WORK, gap=10)
    assert r == Rect(10, 10, 1900, 1060)


# ----- Non-pure actions -----------------------------------------------


@pytest.mark.parametrize(
    "action",
    [
        Action.RESTORE,
        Action.NEXT_DISPLAY,
        Action.PREV_DISPLAY,
        Action.TOGGLE_ALWAYS_ON_TOP,
    ],
)
def test_apply_rejects_non_geometry_actions(action):
    assert not is_geometry_action(action)
    with pytest.raises(KeyError):
        apply(action, WIN, WORK)


# ----- Defaults catalogue --------------------------------------------


def test_advanced_actions_are_discoverable_but_unbound_by_default():
    advanced = set(Action) - set(DEFAULT_SHORTCUTS)
    assert advanced == {
        Action.CENTER_HALF,
        Action.TOP_CENTER_SIXTH,
        Action.BOTTOM_CENTER_SIXTH,
        Action.CENTER_TWO_THIRDS,
        Action.FIRST_FOURTH,
        Action.SECOND_FOURTH,
        Action.THIRD_FOURTH,
        Action.LAST_FOURTH,
        Action.FIRST_THREE_FOURTHS,
        Action.CENTER_THREE_FOURTHS,
        Action.LAST_THREE_FOURTHS,
        Action.TOP_LEFT_THIRD,
        Action.TOP_RIGHT_THIRD,
        Action.BOTTOM_LEFT_THIRD,
        Action.BOTTOM_RIGHT_THIRD,
        Action.TOP_VERTICAL_THIRD,
        Action.MIDDLE_VERTICAL_THIRD,
        Action.BOTTOM_VERTICAL_THIRD,
        Action.TOP_VERTICAL_TWO_THIRDS,
        Action.BOTTOM_VERTICAL_TWO_THIRDS,
        Action.LARGER_WIDTH,
        Action.SMALLER_WIDTH,
        Action.LARGER_HEIGHT,
        Action.SMALLER_HEIGHT,
        Action.MOVE_LEFT,
        Action.MOVE_RIGHT,
        Action.MOVE_UP,
        Action.MOVE_DOWN,
        Action.CENTER_PROMINENTLY,
        Action.HALVE_HEIGHT_UP,
        Action.HALVE_HEIGHT_DOWN,
        Action.HALVE_WIDTH_LEFT,
        Action.HALVE_WIDTH_RIGHT,
        Action.DOUBLE_HEIGHT_UP,
        Action.DOUBLE_HEIGHT_DOWN,
        Action.DOUBLE_WIDTH_LEFT,
        Action.DOUBLE_WIDTH_RIGHT,
        Action.DISPLAY_1,
        Action.DISPLAY_2,
        Action.DISPLAY_3,
        Action.DISPLAY_4,
        Action.DISPLAY_5,
        Action.DISPLAY_6,
        Action.DISPLAY_7,
        Action.DISPLAY_8,
        Action.DISPLAY_9,
    }


def test_default_shortcuts_are_unique():
    seen = set()
    for combo in DEFAULT_SHORTCUTS.values():
        assert combo not in seen, f"duplicate shortcut: {combo}"
        seen.add(combo)


def test_no_default_uses_reserved_win_arrow():
    for combo in DEFAULT_SHORTCUTS.values():
        # Win+arrow is reserved by OS Snap (brief §2).
        assert "win+" not in combo.lower() or "arrow" not in combo.lower()
        # Also no bare meta+arrow combos.
        assert not (combo.startswith("win+") and combo.endswith(("left", "right", "up", "down")))
