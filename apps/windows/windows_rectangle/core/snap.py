"""Drag-to-edge snap-zone detection (brief §2 #13).

Pure logic: given a mouse cursor position and the list of monitors,
decide whether the cursor is inside an edge or corner "hot zone" and,
if so, which `Action` would be applied and what target rect the
footprint-preview overlay should render.

The adapter does the mouse hook + overlay; we just compute.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from ..ports.window_manager import MonitorInfo
from . import monitors as monitors_mod
from .actions import Action, apply
from .geometry import Rect

# Hot-zone thickness in pixels. Rectangle uses ~30px on macOS; Windows
# users running at 1080p won't notice 24px any less.
EDGE_THICKNESS = 24
CORNER_SIZE = 60  # square corner zone — wins over edge if cursor is in both


class SnapZone(str, Enum):
    NONE = "none"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


_ZONE_TO_ACTION: dict[SnapZone, Action] = {
    SnapZone.LEFT: Action.LEFT_HALF,
    SnapZone.RIGHT: Action.RIGHT_HALF,
    SnapZone.TOP: Action.MAXIMIZE,  # Rectangle: drag-to-top = maximize
    SnapZone.BOTTOM: Action.BOTTOM_HALF,
    SnapZone.TOP_LEFT: Action.TOP_LEFT_QUARTER,
    SnapZone.TOP_RIGHT: Action.TOP_RIGHT_QUARTER,
    SnapZone.BOTTOM_LEFT: Action.BOTTOM_LEFT_QUARTER,
    SnapZone.BOTTOM_RIGHT: Action.BOTTOM_RIGHT_QUARTER,
}


@dataclass(frozen=True, slots=True)
class SnapHit:
    """The result of a snap-zone lookup."""

    zone: SnapZone
    monitor: MonitorInfo | None
    action: Action | None
    target: Rect | None  # rect the overlay should preview


def zone_at(
    cursor_x: int,
    cursor_y: int,
    monitor: MonitorInfo,
    *,
    edge: int = EDGE_THICKNESS,
    corner: int = CORNER_SIZE,
) -> SnapZone:
    """Classify a cursor position against one monitor's bounds.

    Uses the full monitor `bounds` (not `work_area`) so that hovering the
    very edge — even over the taskbar — still triggers the snap.
    """
    m = monitor.bounds
    # Quick reject — cursor not on this monitor at all.
    if not (m.left <= cursor_x < m.right and m.top <= cursor_y < m.bottom):
        return SnapZone.NONE

    # Distance from each edge.
    d_left = cursor_x - m.left
    d_right = m.right - 1 - cursor_x
    d_top = cursor_y - m.top
    d_bottom = m.bottom - 1 - cursor_y

    in_left = d_left < edge
    in_right = d_right < edge
    in_top = d_top < edge
    in_bottom = d_bottom < edge

    in_corner_h = d_left < corner or d_right < corner
    in_corner_v = d_top < corner or d_bottom < corner

    # Corner check first — square zone in the corner trumps single edge.
    if in_corner_h and in_corner_v and (in_left or in_right or in_top or in_bottom):
        if d_left < corner and d_top < corner:
            return SnapZone.TOP_LEFT
        if d_right < corner and d_top < corner:
            return SnapZone.TOP_RIGHT
        if d_left < corner and d_bottom < corner:
            return SnapZone.BOTTOM_LEFT
        if d_right < corner and d_bottom < corner:
            return SnapZone.BOTTOM_RIGHT

    if in_left:
        return SnapZone.LEFT
    if in_right:
        return SnapZone.RIGHT
    if in_top:
        return SnapZone.TOP
    if in_bottom:
        return SnapZone.BOTTOM
    return SnapZone.NONE


def find_snap(
    cursor_x: int,
    cursor_y: int,
    monitors: Sequence[MonitorInfo],
    *,
    window: Rect | None = None,
    gap: int = 0,
    edge: int = EDGE_THICKNESS,
    corner: int = CORNER_SIZE,
) -> SnapHit:
    """End-to-end: find the snap zone for `cursor`, compute the preview rect.

    `window` is the currently-dragged window's rect (only used to compute
    the preview accurately for actions where the source matters, e.g. none
    for the standard snap zones).
    """
    if not monitors:
        return SnapHit(SnapZone.NONE, None, None, None)

    # Find which monitor the cursor is over.
    for m in monitors_mod.ordered(monitors):
        zone = zone_at(cursor_x, cursor_y, m, edge=edge, corner=corner)
        if zone is not SnapZone.NONE:
            action = _ZONE_TO_ACTION[zone]
            preview_source = window if window is not None else Rect(0, 0, 0, 0)
            target = apply(action, preview_source, m.work_area, gap)
            return SnapHit(zone, m, action, target)
    return SnapHit(SnapZone.NONE, None, None, None)
