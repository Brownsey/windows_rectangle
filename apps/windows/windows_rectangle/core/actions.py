"""Action catalogue — pure Rect transforms for every brief §2 action.

Each action is a function `(window, work_area, gap) -> Rect` that returns
the target rect for the given window inside the given monitor work area.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

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

    TOP_LEFT_SIXTH = "top_left_sixth"
    TOP_CENTER_SIXTH = "top_center_sixth"
    TOP_RIGHT_SIXTH = "top_right_sixth"
    BOTTOM_LEFT_SIXTH = "bottom_left_sixth"
    BOTTOM_CENTER_SIXTH = "bottom_center_sixth"
    BOTTOM_RIGHT_SIXTH = "bottom_right_sixth"

    FIRST_THIRD = "first_third"
    CENTER_THIRD = "center_third"
    LAST_THIRD = "last_third"
    FIRST_TWO_THIRDS = "first_two_thirds"
    LAST_TWO_THIRDS = "last_two_thirds"
    CENTER_HALF = "center_half"
    CENTER_TWO_THIRDS = "center_two_thirds"
    FIRST_FOURTH = "first_fourth"
    SECOND_FOURTH = "second_fourth"
    THIRD_FOURTH = "third_fourth"
    LAST_FOURTH = "last_fourth"
    FIRST_THREE_FOURTHS = "first_three_fourths"
    CENTER_THREE_FOURTHS = "center_three_fourths"
    LAST_THREE_FOURTHS = "last_three_fourths"
    TOP_LEFT_THIRD = "top_left_third"
    TOP_RIGHT_THIRD = "top_right_third"
    BOTTOM_LEFT_THIRD = "bottom_left_third"
    BOTTOM_RIGHT_THIRD = "bottom_right_third"
    TOP_VERTICAL_THIRD = "top_vertical_third"
    MIDDLE_VERTICAL_THIRD = "middle_vertical_third"
    BOTTOM_VERTICAL_THIRD = "bottom_vertical_third"
    TOP_VERTICAL_TWO_THIRDS = "top_vertical_two_thirds"
    BOTTOM_VERTICAL_TWO_THIRDS = "bottom_vertical_two_thirds"

    MAXIMIZE = "maximize"
    MAXIMIZE_HEIGHT = "maximize_height"
    MAXIMIZE_WIDTH = "maximize_width"
    ALMOST_MAXIMIZE = "almost_maximize"
    CENTER = "center"
    CENTER_PROMINENTLY = "center_prominently"

    LARGER = "larger"
    SMALLER = "smaller"
    LARGER_WIDTH = "larger_width"
    SMALLER_WIDTH = "smaller_width"
    LARGER_HEIGHT = "larger_height"
    SMALLER_HEIGHT = "smaller_height"

    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"

    HALVE_HEIGHT_UP = "halve_height_up"
    HALVE_HEIGHT_DOWN = "halve_height_down"
    HALVE_WIDTH_LEFT = "halve_width_left"
    HALVE_WIDTH_RIGHT = "halve_width_right"
    DOUBLE_HEIGHT_UP = "double_height_up"
    DOUBLE_HEIGHT_DOWN = "double_height_down"
    DOUBLE_WIDTH_LEFT = "double_width_left"
    DOUBLE_WIDTH_RIGHT = "double_width_right"

    RESTORE = "restore"  # handled by history, not a geometry transform
    NEXT_DISPLAY = "next_display"
    PREV_DISPLAY = "prev_display"
    TOGGLE_ALWAYS_ON_TOP = "toggle_always_on_top"
    DISPLAY_1 = "display_1"
    DISPLAY_2 = "display_2"
    DISPLAY_3 = "display_3"
    DISPLAY_4 = "display_4"
    DISPLAY_5 = "display_5"
    DISPLAY_6 = "display_6"
    DISPLAY_7 = "display_7"
    DISPLAY_8 = "display_8"
    DISPLAY_9 = "display_9"


# ---------------------------------------------------------------------
# Default keyboard shortcuts (brief §2)
# ---------------------------------------------------------------------

DEFAULT_SHORTCUTS: dict[Action, str] = {
    Action.LEFT_HALF: "ctrl+alt+left",
    Action.RIGHT_HALF: "ctrl+alt+right",
    Action.TOP_HALF: "ctrl+alt+up",
    Action.BOTTOM_HALF: "ctrl+alt+down",
    Action.TOP_LEFT_QUARTER: "ctrl+alt+u",
    Action.TOP_RIGHT_QUARTER: "ctrl+alt+i",
    Action.BOTTOM_LEFT_QUARTER: "ctrl+alt+j",
    Action.BOTTOM_RIGHT_QUARTER: "ctrl+alt+k",
    Action.TOP_LEFT_SIXTH: "ctrl+insert",
    Action.TOP_RIGHT_SIXTH: "ctrl+pageup",
    Action.BOTTOM_LEFT_SIXTH: "ctrl+delete",
    Action.BOTTOM_RIGHT_SIXTH: "ctrl+pagedown",
    Action.FIRST_THIRD: "ctrl+alt+d",
    Action.CENTER_THIRD: "ctrl+alt+f",
    Action.LAST_THIRD: "ctrl+alt+g",
    Action.FIRST_TWO_THIRDS: "ctrl+alt+e",
    Action.LAST_TWO_THIRDS: "ctrl+alt+t",
    Action.MAXIMIZE: "ctrl+alt+enter",
    Action.MAXIMIZE_HEIGHT: "ctrl+alt+shift+up",
    Action.MAXIMIZE_WIDTH: "ctrl+alt+shift+right",
    Action.ALMOST_MAXIMIZE: "ctrl+alt+shift+enter",
    Action.CENTER: "ctrl+alt+c",
    Action.LARGER: "ctrl+alt+=",
    Action.SMALLER: "ctrl+alt+-",
    Action.RESTORE: "ctrl+alt+backspace",
    Action.NEXT_DISPLAY: "ctrl+alt+.",
    Action.PREV_DISPLAY: "ctrl+alt+,",
    Action.TOGGLE_ALWAYS_ON_TOP: "ctrl+alt+shift+space",
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


def _grid_tile(
    columns: int,
    rows: int,
    column: int,
    row: int,
    column_span: int = 1,
    row_span: int = 1,
) -> TileSpec:
    """Build a normalized tile from integer grid coordinates."""
    return TileSpec(
        _F(column, columns),
        _F(row, rows),
        _F(column + column_span, columns),
        _F(row + row_span, rows),
    )


_TILES: dict[Action, TileSpec] = {
    Action.LEFT_HALF: TileSpec(_F(0), _F(0), _F(1, 2), _F(1)),
    Action.RIGHT_HALF: TileSpec(_F(1, 2), _F(0), _F(1), _F(1)),
    Action.TOP_HALF: TileSpec(_F(0), _F(0), _F(1), _F(1, 2)),
    Action.BOTTOM_HALF: TileSpec(_F(0), _F(1, 2), _F(1), _F(1)),
    Action.TOP_LEFT_QUARTER: TileSpec(_F(0), _F(0), _F(1, 2), _F(1, 2)),
    Action.TOP_RIGHT_QUARTER: TileSpec(_F(1, 2), _F(0), _F(1), _F(1, 2)),
    Action.BOTTOM_LEFT_QUARTER: TileSpec(_F(0), _F(1, 2), _F(1, 2), _F(1)),
    Action.BOTTOM_RIGHT_QUARTER: TileSpec(_F(1, 2), _F(1, 2), _F(1), _F(1)),
    Action.TOP_LEFT_SIXTH: _grid_tile(3, 2, 0, 0),
    Action.TOP_CENTER_SIXTH: _grid_tile(3, 2, 1, 0),
    Action.TOP_RIGHT_SIXTH: _grid_tile(3, 2, 2, 0),
    Action.BOTTOM_LEFT_SIXTH: _grid_tile(3, 2, 0, 1),
    Action.BOTTOM_CENTER_SIXTH: _grid_tile(3, 2, 1, 1),
    Action.BOTTOM_RIGHT_SIXTH: _grid_tile(3, 2, 2, 1),
    Action.FIRST_THIRD: TileSpec(_F(0), _F(0), _F(1, 3), _F(1)),
    Action.CENTER_THIRD: TileSpec(_F(1, 3), _F(0), _F(2, 3), _F(1)),
    Action.LAST_THIRD: TileSpec(_F(2, 3), _F(0), _F(1), _F(1)),
    Action.FIRST_TWO_THIRDS: TileSpec(_F(0), _F(0), _F(2, 3), _F(1)),
    Action.LAST_TWO_THIRDS: TileSpec(_F(1, 3), _F(0), _F(1), _F(1)),
    Action.TOP_VERTICAL_THIRD: _grid_tile(1, 3, 0, 0),
    Action.MIDDLE_VERTICAL_THIRD: _grid_tile(1, 3, 0, 1),
    Action.BOTTOM_VERTICAL_THIRD: _grid_tile(1, 3, 0, 2),
    Action.TOP_VERTICAL_TWO_THIRDS: _grid_tile(1, 3, 0, 0, row_span=2),
    Action.BOTTOM_VERTICAL_TWO_THIRDS: _grid_tile(1, 3, 0, 1, row_span=2),
    Action.MAXIMIZE: TileSpec(_F(0), _F(0), _F(1), _F(1)),
}


# Rectangle treats these as horizontal bands on landscape displays and
# vertical bands on portrait displays. Keeping the fractions declarative makes
# fourths and centered spans share one tested calculation path.
_ORIENTED_BANDS: dict[Action, tuple[Fraction, Fraction]] = {
    Action.CENTER_HALF: (_F(1, 4), _F(3, 4)),
    Action.CENTER_TWO_THIRDS: (_F(1, 6), _F(5, 6)),
    Action.FIRST_FOURTH: (_F(0), _F(1, 4)),
    Action.SECOND_FOURTH: (_F(1, 4), _F(1, 2)),
    Action.THIRD_FOURTH: (_F(1, 2), _F(3, 4)),
    Action.LAST_FOURTH: (_F(3, 4), _F(1)),
    Action.FIRST_THREE_FOURTHS: (_F(0), _F(3, 4)),
    Action.CENTER_THREE_FOURTHS: (_F(1, 8), _F(7, 8)),
    Action.LAST_THREE_FOURTHS: (_F(1, 4), _F(1)),
}


_ORIENTED_TILES: dict[Action, tuple[TileSpec, TileSpec]] = {
    # Landscape uses a 3x2 conceptual grid with two-column spans; portrait
    # rotates that idea to a 2x3 grid with two-row spans.
    Action.TOP_LEFT_THIRD: (
        _grid_tile(3, 2, 0, 0, column_span=2),
        _grid_tile(2, 3, 0, 0, row_span=2),
    ),
    Action.TOP_RIGHT_THIRD: (
        _grid_tile(3, 2, 1, 0, column_span=2),
        _grid_tile(2, 3, 1, 0, row_span=2),
    ),
    Action.BOTTOM_LEFT_THIRD: (
        _grid_tile(3, 2, 0, 1, column_span=2),
        _grid_tile(2, 3, 0, 1, row_span=2),
    ),
    Action.BOTTOM_RIGHT_THIRD: (
        _grid_tile(3, 2, 1, 1, column_span=2),
        _grid_tile(2, 3, 1, 1, row_span=2),
    ),
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
            left=spec.left,
            top=spec.top,
            right=spec.right,
            bottom=spec.bottom,
        )
        edges = tile_edges(spec.left, spec.top, spec.right, spec.bottom)
        return apply_gap(work_area, tile, edges, gap)

    return handler


def _oriented_band_handler(action: Action) -> ActionFn:
    start, end = _ORIENTED_BANDS[action]

    def handler(window: Rect, work_area: Rect, gap: int) -> Rect:
        if work_area.width >= work_area.height:
            tile = fraction_rect(work_area, left=start, right=end)
            edges = tile_edges(start, 0, end, 1)
        else:
            tile = fraction_rect(work_area, top=start, bottom=end)
            edges = tile_edges(0, start, 1, end)
        return apply_gap(work_area, tile, edges, gap)

    return handler


def _oriented_tile_handler(action: Action) -> ActionFn:
    landscape, portrait = _ORIENTED_TILES[action]

    def handler(window: Rect, work_area: Rect, gap: int) -> Rect:
        spec = landscape if work_area.width >= work_area.height else portrait
        tile = fraction_rect(
            work_area,
            left=spec.left,
            top=spec.top,
            right=spec.right,
            bottom=spec.bottom,
        )
        return apply_gap(
            work_area,
            tile,
            tile_edges(spec.left, spec.top, spec.right, spec.bottom),
            gap,
        )

    return handler


def maximize_height(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Stretch window to full work-area height; keep horizontal position/width."""
    target = Rect(window.x, work_area.y, window.width, work_area.height)
    # Apply outer gap top/bottom only; horizontal sides untouched.
    if gap > 0:
        target = Rect(target.x, target.y + gap, target.width, max(1, target.height - 2 * gap))
    return target.clamp_to(work_area)


def maximize_width(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Stretch to the work-area width while preserving vertical geometry."""
    target = Rect(work_area.x, window.y, work_area.width, window.height)
    if gap > 0:
        target = Rect(target.x + gap, target.y, max(1, target.width - 2 * gap), target.height)
    return target.clamp_to(work_area)


def almost_maximize(
    window: Rect,
    work_area: Rect,
    gap: int,
    *,
    scale: float = ALMOST_MAXIMIZE_SCALE,
) -> Rect:
    """A scaled-down maximize — Rectangle uses ~85% by default.

    `scale` overrides the default so the user-configurable
    `Settings.almost_maximize_scale` actually takes effect (previously
    the prefs slider was wired to nothing — the module-level constant
    was always used).
    """
    w = int(work_area.width * scale)
    h = int(work_area.height * scale)
    base = Rect(0, 0, w, h)
    return base.centered_in(work_area)


def center(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Move (do not resize) window to center of work area."""
    return window.centered_in(work_area)


def center_prominently(window: Rect, work_area: Rect, gap: int) -> Rect:
    """Center horizontally and place the window in the upper visual quarter."""
    width = min(window.width, work_area.width)
    height = min(window.height, work_area.height)
    return Rect(
        work_area.x + (work_area.width - width) // 2,
        work_area.y + (work_area.height - height) // 4,
        width,
        height,
    )


def larger(window: Rect, work_area: Rect, gap: int) -> Rect:
    return _resize_step(window, work_area, +LARGER_SMALLER_STEP)


def smaller(window: Rect, work_area: Rect, gap: int) -> Rect:
    return _resize_step(window, work_area, -LARGER_SMALLER_STEP)


def _resize_dimension(window: Rect, work_area: Rect, delta: int, *, width: bool) -> Rect:
    new_width = window.width + delta if width else window.width
    new_height = window.height if width else window.height + delta
    new_width = min(work_area.width, max(MIN_WINDOW_W, new_width))
    new_height = min(work_area.height, max(MIN_WINDOW_H, new_height))
    return Rect(
        window.center_x - new_width // 2,
        window.center_y - new_height // 2,
        new_width,
        new_height,
    ).clamp_to(work_area)


def _move_to_edge(window: Rect, work_area: Rect, action: Action) -> Rect:
    width = min(window.width, work_area.width)
    height = min(window.height, work_area.height)
    if action in (Action.MOVE_LEFT, Action.MOVE_RIGHT):
        x = work_area.left if action is Action.MOVE_LEFT else work_area.right - width
        y = work_area.y + (work_area.height - height) // 2
    else:
        x = work_area.x + (work_area.width - width) // 2
        y = work_area.top if action is Action.MOVE_UP else work_area.bottom - height
    return Rect(x, y, width, height)


def _scale_anchored(window: Rect, work_area: Rect, action: Action) -> Rect:
    halves = action in {
        Action.HALVE_HEIGHT_UP,
        Action.HALVE_HEIGHT_DOWN,
        Action.HALVE_WIDTH_LEFT,
        Action.HALVE_WIDTH_RIGHT,
    }
    changes_width = action in {
        Action.HALVE_WIDTH_LEFT,
        Action.HALVE_WIDTH_RIGHT,
        Action.DOUBLE_WIDTH_LEFT,
        Action.DOUBLE_WIDTH_RIGHT,
    }
    factor = _F(1, 2) if halves else _F(2)
    width, height = window.width, window.height
    if changes_width:
        width = max(MIN_WINDOW_W, round(window.width * factor))
    else:
        height = max(MIN_WINDOW_H, round(window.height * factor))
    width = min(width, work_area.width)
    height = min(height, work_area.height)
    x, y = window.x, window.y
    if action in {Action.HALVE_WIDTH_RIGHT, Action.DOUBLE_WIDTH_LEFT}:
        x = window.right - width
    if action in {Action.HALVE_HEIGHT_DOWN, Action.DOUBLE_HEIGHT_UP}:
        y = window.bottom - height
    return Rect(x, y, width, height).clamp_to(work_area)


def _anchored_handler(action: Action) -> ActionFn:
    def handler(window: Rect, work_area: Rect, gap: int) -> Rect:
        return _scale_anchored(window, work_area, action)

    return handler


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
    **{a: _oriented_band_handler(a) for a in _ORIENTED_BANDS},
    **{a: _oriented_tile_handler(a) for a in _ORIENTED_TILES},
    Action.MAXIMIZE_HEIGHT: maximize_height,
    Action.MAXIMIZE_WIDTH: maximize_width,
    Action.ALMOST_MAXIMIZE: almost_maximize,
    Action.CENTER: center,
    Action.CENTER_PROMINENTLY: center_prominently,
    Action.LARGER: larger,
    Action.SMALLER: smaller,
    Action.LARGER_WIDTH: lambda window, work, gap: _resize_dimension(
        window, work, LARGER_SMALLER_STEP, width=True
    ),
    Action.SMALLER_WIDTH: lambda window, work, gap: _resize_dimension(
        window, work, -LARGER_SMALLER_STEP, width=True
    ),
    Action.LARGER_HEIGHT: lambda window, work, gap: _resize_dimension(
        window, work, LARGER_SMALLER_STEP, width=False
    ),
    Action.SMALLER_HEIGHT: lambda window, work, gap: _resize_dimension(
        window, work, -LARGER_SMALLER_STEP, width=False
    ),
    Action.MOVE_LEFT: lambda window, work, gap: _move_to_edge(window, work, Action.MOVE_LEFT),
    Action.MOVE_RIGHT: lambda window, work, gap: _move_to_edge(window, work, Action.MOVE_RIGHT),
    Action.MOVE_UP: lambda window, work, gap: _move_to_edge(window, work, Action.MOVE_UP),
    Action.MOVE_DOWN: lambda window, work, gap: _move_to_edge(window, work, Action.MOVE_DOWN),
    **{
        action: _anchored_handler(action)
        for action in (
            Action.HALVE_HEIGHT_UP,
            Action.HALVE_HEIGHT_DOWN,
            Action.HALVE_WIDTH_LEFT,
            Action.HALVE_WIDTH_RIGHT,
            Action.DOUBLE_HEIGHT_UP,
            Action.DOUBLE_HEIGHT_DOWN,
            Action.DOUBLE_WIDTH_LEFT,
            Action.DOUBLE_WIDTH_RIGHT,
        )
    },
}


def apply(
    action: Action,
    window: Rect,
    work_area: Rect,
    gap: int = 0,
    *,
    almost_maximize_scale: float | None = None,
) -> Rect:
    """Compute the target rect for `action` applied to `window` in `work_area`.

    Raises KeyError for actions that aren't pure geometry transforms
    (RESTORE, NEXT_DISPLAY, PREV_DISPLAY) — those are dispatcher-level.

    `almost_maximize_scale`:
      - Honoured only for `Action.ALMOST_MAXIMIZE`; other actions ignore it.
      - `None` (default) → use the module-level `ALMOST_MAXIMIZE_SCALE`
        constant, matching the pre-prefs-wiring behaviour.
      - Any float → overrides for this dispatch (settings-driven path).
      Kept as a kwarg so callers that don't care about the scale don't
      need to import the constant just to repeat it.
    """
    try:
        handler = _HANDLERS[action]
    except KeyError as e:
        raise KeyError(f"{action} is not a pure geometry action") from e
    if action is Action.ALMOST_MAXIMIZE and almost_maximize_scale is not None:
        return almost_maximize(window, work_area, gap, scale=almost_maximize_scale)
    return handler(window, work_area, gap)


def is_geometry_action(action: Action) -> bool:
    return action in _HANDLERS
