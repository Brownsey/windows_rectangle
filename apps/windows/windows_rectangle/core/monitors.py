"""Pure multi-monitor logic — no OS calls.

Adapter supplies a list of `MonitorInfo` and the dispatcher uses these
functions to pick which monitor a window should move to.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..ports.window_manager import MonitorInfo
from .geometry import Rect, apply_relative_position, relative_position


def _sort_key(m: MonitorInfo) -> tuple[int, int]:
    """Left-to-right, top-to-bottom — stable ordering for next/prev cycling."""
    return (m.bounds.left, m.bounds.top)


def ordered(monitors: Sequence[MonitorInfo]) -> list[MonitorInfo]:
    """Return monitors in a deterministic left-to-right, top-to-bottom order."""
    return sorted(monitors, key=_sort_key)


def index_of(monitors: Sequence[MonitorInfo], target: MonitorInfo) -> int:
    """Position of `target` in `ordered(monitors)`. Returns 0 if not found."""
    seq = ordered(monitors)
    for i, m in enumerate(seq):
        if m.handle == target.handle:
            return i
    return 0


def neighbor(
    monitors: Sequence[MonitorInfo],
    current: MonitorInfo,
    *,
    direction: int,
) -> MonitorInfo:
    """Pick the next (`+1`) or previous (`-1`) monitor, wrapping.

    With only one monitor connected, returns the current one unchanged.
    """
    if direction not in (-1, 1):
        raise ValueError(f"direction must be +/-1, got {direction}")
    seq = ordered(monitors)
    if not seq:
        return current
    # Index lookup inline — calling index_of() would re-sort the list.
    idx = next(
        (i for i, m in enumerate(seq) if m.handle == current.handle),
        0,
    )
    return seq[(idx + direction) % len(seq)]


def move_to_monitor(
    window: Rect,
    source: MonitorInfo,
    destination: MonitorInfo,
) -> Rect:
    """Move `window` so it occupies the same *relative* fraction of `destination`.

    Implements brief §7 phase P3: a window that was the right-half of mon A
    becomes the right-half of mon B, regardless of resolution/DPI differences.
    """
    if source.handle == destination.handle:
        return window
    fracs = relative_position(window, source.work_area)
    return apply_relative_position(fracs, destination.work_area)


def overlap_area(window: Rect, monitor: MonitorInfo) -> int:
    """Pixel area of `window` ∩ `monitor.bounds` — used as a tie-break.

    Picks the monitor that contains the largest part of the window.
    """
    return window.clamp_to(monitor.bounds).area


def best_monitor_for(window: Rect, monitors: Sequence[MonitorInfo]) -> MonitorInfo | None:
    """Return the monitor whose intersection with `window` is largest.

    Used to recover the monitor when the adapter can't tell us directly
    (e.g. windows hanging across screen borders).
    """
    if not monitors:
        return None
    best: tuple[int, MonitorInfo] | None = None
    for m in ordered(monitors):
        area = overlap_area(window, m)
        if best is None or area > best[0]:
            best = (area, m)
    assert best is not None
    return best[1]
