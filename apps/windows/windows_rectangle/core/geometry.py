"""Pure window geometry math — no OS calls.

Coordinates are integers in physical pixels relative to a monitor's
work area (i.e. excluding the Windows taskbar).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class Rect:
    """An axis-aligned rectangle in integer pixels.

    `x`, `y` are the top-left; `width`, `height` extend right/down.
    """

    x: int
    y: int
    width: int
    height: int

    # ----- factories ---------------------------------------------------

    @classmethod
    def from_ltrb(cls, left: int, top: int, right: int, bottom: int) -> Rect:
        return cls(left, top, right - left, bottom - top)

    # ----- properties --------------------------------------------------

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def is_empty(self) -> bool:
        return self.width <= 0 or self.height <= 0

    # ----- structural helpers -----------------------------------------

    def with_gap(self, gap: int) -> Rect:
        """Inset all sides by `gap` pixels. A zero/negative gap is a no-op."""
        if gap <= 0:
            return self
        return Rect(
            self.x + gap,
            self.y + gap,
            max(0, self.width - 2 * gap),
            max(0, self.height - 2 * gap),
        )

    def clamp_to(self, bounds: Rect) -> Rect:
        """Clip this rect so it lies entirely within `bounds`."""
        left = max(self.left, bounds.left)
        top = max(self.top, bounds.top)
        right = min(self.right, bounds.right)
        bottom = min(self.bottom, bounds.bottom)
        if right <= left or bottom <= top:
            return Rect(bounds.x, bounds.y, 0, 0)
        return Rect.from_ltrb(left, top, right, bottom)

    def scaled(self, factor: float) -> Rect:
        """Resize about the center by `factor`. Width/height clamped to >= 1."""
        new_w = max(1, int(round(self.width * factor)))
        new_h = max(1, int(round(self.height * factor)))
        new_x = self.center_x - new_w // 2
        new_y = self.center_y - new_h // 2
        return Rect(new_x, new_y, new_w, new_h)

    def centered_in(self, bounds: Rect) -> Rect:
        """Move (without resizing) so this rect is centered inside `bounds`."""
        x = bounds.x + (bounds.width - self.width) // 2
        y = bounds.y + (bounds.height - self.height) // 2
        return Rect(x, y, self.width, self.height)


@dataclass(frozen=True, slots=True)
class EdgeFlags:
    """Which edges of a tile abut a neighbour (and so need a half-gap)."""

    left: bool = False
    top: bool = False
    right: bool = False
    bottom: bool = False


# ---------------------------------------------------------------------
# Fraction-based tiling
# ---------------------------------------------------------------------


def fraction_rect(
    work_area: Rect,
    *,
    left: Fraction | float = 0,
    top: Fraction | float = 0,
    right: Fraction | float = 1,
    bottom: Fraction | float = 1,
) -> Rect:
    """Carve a sub-rect out of `work_area` using normalised [0,1] coords.

    Integer pixel boundaries are derived with `round()` so that adjacent
    tiles (e.g. left-half right-edge and right-half left-edge) meet
    cleanly without one-pixel gaps or overlaps.
    """
    if not (0 <= float(left) <= float(right) <= 1):
        raise ValueError(f"left/right out of range: {left}, {right}")
    if not (0 <= float(top) <= float(bottom) <= 1):
        raise ValueError(f"top/bottom out of range: {top}, {bottom}")

    x0 = work_area.x + round(float(left) * work_area.width)
    x1 = work_area.x + round(float(right) * work_area.width)
    y0 = work_area.y + round(float(top) * work_area.height)
    y1 = work_area.y + round(float(bottom) * work_area.height)
    return Rect.from_ltrb(x0, y0, x1, y1)


def tile_edges(
    left: Fraction | float, top: Fraction | float, right: Fraction | float, bottom: Fraction | float
) -> EdgeFlags:
    """Derive which edges of a tile abut a neighbour vs the work-area boundary."""
    return EdgeFlags(
        left=float(left) > 0,
        top=float(top) > 0,
        right=float(right) < 1,
        bottom=float(bottom) < 1,
    )


def apply_gap(work_area: Rect, tile: Rect, edges: EdgeFlags, gap: int) -> Rect:
    """Apply an outer gap (around the work area) and an inner half-gap per shared edge.

    Rectangle's gap setting affects both the screen-edge inset and the gutter
    between tiles. Each interior gutter is `gap` wide (each neighbour
    contributes half). Each outer edge is inset by the full `gap`.
    """
    if gap <= 0:
        return tile
    half = gap // 2
    other = gap - half  # ceil half — ensures total interior gutter == gap when odd
    left = tile.left + (half if edges.left else gap)
    top = tile.top + (half if edges.top else gap)
    right = tile.right - (other if edges.right else gap)
    bottom = tile.bottom - (other if edges.bottom else gap)
    return Rect.from_ltrb(left, top, max(left, right), max(top, bottom))


def union(rects: Iterable[Rect]) -> Rect:
    """Smallest rect containing all given rects. Empty iterable -> 0x0 rect."""
    rs = list(rects)
    if not rs:
        return Rect(0, 0, 0, 0)
    left = min(r.left for r in rs)
    top = min(r.top for r in rs)
    right = max(r.right for r in rs)
    bottom = max(r.bottom for r in rs)
    return Rect.from_ltrb(left, top, right, bottom)


def relative_position(window: Rect, monitor: Rect) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """Express `window` as fractions of `monitor` (l, t, r, b).

    Used when moving a window between monitors to preserve its relative
    footprint — brief §7 phase P3.
    """
    if monitor.width <= 0 or monitor.height <= 0:
        return Fraction(0), Fraction(0), Fraction(1), Fraction(1)
    return (
        Fraction(window.left - monitor.left, monitor.width),
        Fraction(window.top - monitor.top, monitor.height),
        Fraction(window.right - monitor.left, monitor.width),
        Fraction(window.bottom - monitor.top, monitor.height),
    )


def apply_relative_position(
    fractions: tuple[Fraction, Fraction, Fraction, Fraction],
    new_monitor: Rect,
) -> Rect:
    """Inverse of `relative_position` against a new monitor."""
    l, t, r, b = fractions
    return fraction_rect(new_monitor, left=l, top=t, right=r, bottom=b)
