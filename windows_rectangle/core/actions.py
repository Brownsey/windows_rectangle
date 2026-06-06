"""Action catalogue — pure Rect transforms for every brief §2 action.

Each action is a function `(window, work_area, gap) -> Rect` that returns
the target rect for the given window inside the given monitor work area.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Callable

from .geometry import Rect, apply_gap, fraction_rect, tile_edges

_F = Fraction


# Scale factors -----------------------------------------------------------

ALMOST_MAXIMIZE_SCALE = 0.85
LARGER_SMALLER_STEP = 30  # pixels per side per press (Rectangle default)
MIN_WINDOW_W = 80
MIN_WINDOW_H = 60


class Action(str, Enum):
    """Stable identifier for every supported action."""

    LEFT_HALF = "left_half"
    RIGHT_HALF = "right_half"
    TOP_HALF = "top_half"
    BOTTOM_HALF = "bottom_half"

    TOP_LEFT_QUARTER = "top_left_quarter"
    TOP_RIGHT_QUARTER = "top_right_quarter"
    BOTTOM_LEFT_QUARTER = "bottom_left_quarter"
    BOTTOM_RIGHT_QUARTER = "bottom_right_quarter"

    FIRST_THIRD = "first_third"
    CENTER_THIRD = "center_third"
    LAST_THIRD = "last_third"
    FIRST_TWO_THIRDS = "first_two_thirds"
    LAST_TWO_THIRDS = "last_two_thirds"

    MAXIMIZE = "maximize"
    MAXIMIZE_HEIGHT = "maximize_height"
    ALMOST_MAXIMIZE = "almost_maximize"
    CENTER = "center"

    LARGER = "larger"
    SMALLER = "smaller"

    RESTORE = "restore"  # handled by history, not a geometry transform
    NEXT_DISPLAY = "next_display"
    PREV_DISPLAY = "prev_display"


# ---------------------------------------------------------------------
# Default keyboard shortcuts (brief §2)
# ---------------------------------------------------------------------

DEFAULT_SHORTCUTS: dict[Action, str] = {
    Action.LEFT_HALF:           "ctrl+alt+left",
    Action.RIGHT_HALF:          "ctrl+alt+right",
    Action.TOP_HALF:            "ctrl+alt+up",
    Action.BOTTOM_HALF:         "ctrl+alt+down",
    Action.TOP_LEFT_QUARTER:    "ctrl+alt+u",
    Action.TOP_RIGHT_QUARTER:   "ctrl+alt+i",
    Action.BOTTOM_LEFT_QUARTER: "ctrl+alt+j",
    Action.BOTTOM_RIGHT_QUARTER:"ctrl+alt+k",
    Action.FIRST_THIRD:         "ctrl+alt+d",
    Action.CENTER_THIRD:        "ctrl+alt+f",
    Action.LAST_THIRD:          "ctrl+alt+g",
    Action.FIRST_TWO_THIRDS:    "ctrl+alt+e",
    Action.LAST_TWO_THIRDS:     "ctrl+alt+t",
    Action.MAXIMIZE:            "ctrl+alt+enter",
    Action.MAXIMIZE_HEIGHT:     "ctrl+alt+shift+up",
    Action.ALMOST_MAXIMIZE:     "ctrl+alt+shift+enter",
    Action.CENTER:              "ctrl+alt+c",
    Action.LARGER:              "ctrl+alt+=",
    Action.SMALLER:             "ctrl+alt+-",
    Action.RESTORE:             "ctrl+alt+backspace",
    Action.NEXT_DISPLAY:        "ctrl+alt+.",
    Action.PREV_DISPLAY:        "ctrl+alt+,",
}


# ---------------------------------------------------------------------
# Tile-spec table — fractional rectangles for fixed-position actions
# ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TileSpec:
    """Normalised tile in [0,1]x[0,1] coordinates of the work area."""

    left: Fraction
    top: Fraction
    right: Fraction
    bottom: Fraction


_TILES: dict[Action, TileSpec] = {
    Action.LEFT_HALF:            TileSpec(_F(0),    _F(0),   _F(1, 2), _F(1)),
    Action.RIGHT_HALF:           TileSpec(_F(1, 2), _F(0),   _F(1),    _F(1)),
    Action.TOP_HALF:             TileSpec(_F(0),    _F(0),   _F(1),    _F(1, 2)),
    Action.BOTTOM_HALF:          TileSpec(_F(0),    _F(1, 2),_F(1),    _F(1)),

    Action.TOP_LEFT_QUARTER:     TileSpec(_F(0),    _F(0),   _F(1, 2), _F(1, 2)),
    Action.TOP_RIGHT_QUARTER:    TileSpec(_F(1, 2), _F(0),   _F(1),    _F(1, 2)),
    Action.BOTTOM_LEFT_QUARTER:  TileSpec(_F(0),    _F(1, 2),_F(1, 2), _F(1)),
    Action.BOTTOM_RIGHT_QUARTER: TileSpec(_F(1, 2), _F(1, 2),_F(1),    _F(1)),

    Action.FIRST_THIRD:          TileSpec(_F(0),    _F(0),   _F(1, 3), _F(1)),
    Action.CENTER_THIRD:         TileSpec(_F(1, 3), _F(0),   _F(2, 3), _F(1)),
    Action.LAST_THIRD:           TileSpec(_F(2, 3), _F(0),   _F(1),    _F(1)),
    Action.FIRST_TWO_THIRDS:     TileSpec(_F(0),    _F(0),   _F(2, 3), _F(1)),
    Action.LAST_TWO_THIRDS:      TileSpec(_F(1, 3), _F(0),   _F(1),    _F(1)),

    Action.MAXIMIZE:             TileSpec(_F(0),    _F(0),   _F(1),    _F(1)),
}


# ---------------------------------------------------------------------
# Action handler signature
# ---------------------------------------------------------------------

ActionFn = Callable[[Rect, Rect, int], Rect]


def _tile_handler(action: Action) -> ActionFn:
    spec = _TILES[action]

    def handler(window: Rect, work_area: Rect, gap: int) -> Rect:
        tile = fraction_rect(
            work_area,
            left=spec.left, top=spec.top, right=spec.right, bottom=spec.bottom,
        )
        return apply_gap(work_area, tile, tile_edges(spec.left, spec.top, spec.right, spec.bottom), gap)

    return handler


def maximize_height(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Stretch window to full work-area height; keep horizontal position/width."""
    target = Rect(window.x, work_area.y, window.width, work_area.height)
    # Apply outer gap top/bottom only; horizontal sides untouched.
    if gap > 0:
        target = Rect(target.x, target.y + gap, target.width, max(1, target.height - 2 * gap))
    return target.clamp_to(work_area)


def almost_maximize(window: Rect, work_area: Rect, gap: int) -> Rect:
    """A scaled-down maximize — Rectangle uses ~85% by default."""
    w = int(work_area.width * ALMOST_MAXIMIZE_SCALE)
    h = int(work_area.height * ALMOST_MAXIMIZE_SCALE)
    base = Rect(0, 0, w, h)
    return base.centered_in(work_area)


def center(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Move (do not resize) window to center of work area."""
    return window.centered_in(work_area)


def larger(window: Rect, work_area: Rect, gap: int) -> Rect:
    return _resize_step(window, work_area, +LARGER_SMALLER_STEP)


def smaller(window: Rect, work_area: Rect, gap: int) -> Rect:
    return _resize_step(window, work_area, -LARGER_SMALLER_STEP)


def _resize_step(window: Rect, work_area: Rect, delta: int) -> Rect:
    """Grow/shrink each side by `delta`, keeping the center stable."""
    new_w = max(MIN_WINDOW_W, window.width + 2 * delta)
    new_h = max(MIN_WINDOW_H, window.height + 2 * delta)
    # Cap to work area when growing.
    new_w = min(new_w, work_area.width)
    new_h = min(new_h, work_area.height)
    cx, cy = window.center_x, window.center_y
    new_x = cx - new_w // 2
    new_y = cy - new_h // 2
    return Rect(new_x, new_y, new_w, new_h).clamp_to(work_area)


# ---------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------

_HANDLERS: dict[Action, ActionFn] = {
    **{a: _tile_handler(a) for a in _TILES},
    Action.MAXIMIZE_HEIGHT: maximize_height,
    Action.ALMOST_MAXIMIZE: almost_maximize,
    Action.CENTER: center,
    Action.LARGER: larger,
    Action.SMALLER: smaller,
}


def apply(action: Action, window: Rect, work_area: Rect, gap: int = 0) -> Rect:
    """Compute the target rect for `action` applied to `window` in `work_area`.

    Raises KeyError for actions that aren't pure geometry transforms
    (RESTORE, NEXT_DISPLAY, PREV_DISPLAY) — those are dispatcher-level.
    """
    try:
        handler = _HANDLERS[action]
    except KeyError as e:
        raise KeyError(f"{action} is not a pure geometry action") from e
    return handler(window, work_area, gap)


def is_geometry_action(action: Action) -> bool:
    return action in _HANDLERS
