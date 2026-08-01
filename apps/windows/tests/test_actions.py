"""Tests for windows_rectangle.core.actions."""

import pytest
from windows_rectangle.core.actions import (
    ALMOST_MAXIMIZE_SCALE,
    DEFAULT_SHORTCUTS,
    MAX_ALMOST_MAXIMIZE_SCALE,
    MIN_ALMOST_MAXIMIZE_SCALE,
    Action,
    apply,
    clamp_almost_maximize_scale,
    is_geometry_action,
)
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.shortcuts import is_reserved

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


# ----- Sixths ---------------------------------------------------------


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
    assert r.x == WORK.x
    assert r.width == WORK.width
    assert r.y == WIN.y
    assert r.height == WIN.height


def test_maximize_width_applies_horizontal_gap_only():
    assert apply(Action.MAXIMIZE_WIDTH, WIN, WORK, gap=10) == Rect(10, WIN.y, 1900, WIN.height)


def test_almost_maximize_centered_and_smaller():
    r = apply(Action.ALMOST_MAXIMIZE, WIN, WORK)
    assert r.width == int(WORK.width * ALMOST_MAXIMIZE_SCALE)
    assert r.height == int(WORK.height * ALMOST_MAXIMIZE_SCALE)
    assert r.width < WORK.width
    assert r.height < WORK.height
    assert abs(r.center_x - WORK.center_x) <= 1
    assert abs(r.center_y - WORK.center_y) <= 1


def test_almost_maximize_uses_custom_scale():
    r = apply(Action.ALMOST_MAXIMIZE, WIN, WORK, almost_maximize_scale=0.75)
    assert r.width == 1440
    assert r.height == 810
    assert abs(r.center_x - WORK.center_x) <= 1
    assert abs(r.center_y - WORK.center_y) <= 1


def test_almost_maximize_scale_is_clamped():
    assert clamp_almost_maximize_scale(0.1) == MIN_ALMOST_MAXIMIZE_SCALE
    assert clamp_almost_maximize_scale(2.0) == MAX_ALMOST_MAXIMIZE_SCALE
    assert clamp_almost_maximize_scale(0.8) == 0.8
    assert apply(Action.ALMOST_MAXIMIZE, WIN, WORK, almost_maximize_scale=2.0) == WORK


def test_center_doesnt_resize():
    r = apply(Action.CENTER, WIN, WORK)
    assert (r.width, r.height) == (WIN.width, WIN.height)
    assert abs(r.center_x - WORK.center_x) <= 1


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


def test_every_action_has_default_shortcut():
    for a in Action:
        assert a in DEFAULT_SHORTCUTS, f"missing shortcut for {a}"


def test_default_shortcuts_enable_every_action():
    for action, combo in DEFAULT_SHORTCUTS.items():
        assert combo, f"disabled default shortcut for {action}"


def test_default_shortcuts_are_unique():
    seen = set()
    for combo in DEFAULT_SHORTCUTS.values():
        if not combo:
            continue
        assert combo not in seen, f"duplicate shortcut: {combo}"
        seen.add(combo)


def test_no_default_uses_reserved_shortcut():
    for combo in DEFAULT_SHORTCUTS.values():
        if not combo:
            continue
        assert not is_reserved(combo)


def test_active_default_shortcuts_match_recommended_profile():
    assert _enabled_defaults() == {
        Action.LEFT_HALF: "ctrl+alt+left",
        Action.RIGHT_HALF: "ctrl+alt+right",
        Action.TOP_HALF: "ctrl+alt+up",
        Action.BOTTOM_HALF: "ctrl+alt+down",
        Action.FIRST_THIRD: "ctrl+alt+d",
        Action.CENTER_THIRD: "ctrl+alt+f",
        Action.LAST_THIRD: "ctrl+alt+g",
        Action.FIRST_TWO_THIRDS: "ctrl+alt+e",
        Action.LAST_TWO_THIRDS: "ctrl+alt+t",
        Action.ALMOST_MAXIMIZE: "ctrl+alt+shift+enter",
        Action.TOP_LEFT_QUARTER: "ctrl+alt+u",
        Action.TOP_RIGHT_QUARTER: "ctrl+alt+i",
        Action.BOTTOM_LEFT_QUARTER: "ctrl+alt+j",
        Action.BOTTOM_RIGHT_QUARTER: "ctrl+alt+k",
        Action.TOP_LEFT_SIXTH: "ctrl+alt+insert",
        Action.TOP_RIGHT_SIXTH: "ctrl+alt+pageup",
        Action.BOTTOM_LEFT_SIXTH: "ctrl+alt+shift+delete",
        Action.BOTTOM_RIGHT_SIXTH: "ctrl+alt+pagedown",
        Action.MAXIMIZE: "ctrl+alt+enter",
        Action.MAXIMIZE_HEIGHT: "ctrl+alt+shift+up",
        Action.MAXIMIZE_WIDTH: "ctrl+alt+shift+right",
        Action.CENTER: "ctrl+alt+c",
        Action.LARGER: "ctrl+alt+=",
        Action.SMALLER: "ctrl+alt+-",
        Action.RESTORE: "ctrl+alt+backspace",
        Action.NEXT_DISPLAY: "ctrl+alt+.",
        Action.PREV_DISPLAY: "ctrl+alt+,",
        Action.TOGGLE_ALWAYS_ON_TOP: "ctrl+alt+shift+space",
    }


def _enabled_defaults() -> dict[Action, str]:
    return {action: combo for action, combo in DEFAULT_SHORTCUTS.items() if combo}
