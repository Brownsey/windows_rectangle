"""Pure models and matching for reusable multi-window workspaces.

Coordinates use integer basis points (0..10_000), avoiding float drift while
remaining independent of monitor resolution and DPI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from .geometry import Rect

BASIS = 10_000


def new_id() -> str:
    """Return a compact stable id suitable for persisted user objects."""
    return uuid4().hex


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if not (0 <= self.left < self.right <= BASIS):
            raise ValueError("workspace rectangle must have 0 <= left < right <= 10000")
        if not (0 <= self.top < self.bottom <= BASIS):
            raise ValueError("workspace rectangle must have 0 <= top < bottom <= 10000")

    def to_rect(self, work_area: Rect) -> Rect:
        """Convert to physical pixels, sharing exact boundaries with neighbours."""
        x0 = work_area.x + round(self.left * work_area.width / BASIS)
        x1 = work_area.x + round(self.right * work_area.width / BASIS)
        y0 = work_area.y + round(self.top * work_area.height / BASIS)
        y1 = work_area.y + round(self.bottom * work_area.height / BASIS)
        return Rect.from_ltrb(x0, y0, x1, y1)

    @classmethod
    def from_rect(cls, rect: Rect, work_area: Rect) -> NormalizedRect:
        if work_area.is_empty():
            raise ValueError("cannot capture a workspace rectangle from an empty work area")
        clipped = rect.clamp_to(work_area)
        if clipped.is_empty():
            raise ValueError("window does not overlap the selected monitor work area")
        return cls(
            round((clipped.left - work_area.left) * BASIS / work_area.width),
            round((clipped.top - work_area.top) * BASIS / work_area.height),
            round((clipped.right - work_area.left) * BASIS / work_area.width),
            round((clipped.bottom - work_area.top) * BASIS / work_area.height),
        )


@dataclass(frozen=True, slots=True)
class WindowIdentity:
    handle: object
    title: str
    process_name: str


@dataclass(frozen=True, slots=True)
class WindowMatcher:
    """Layered identity rule; process + title is safer than either alone."""

    process_name: str = ""
    title_contains: str = ""
    title_regex: str = ""

    def __post_init__(self) -> None:
        if not any(
            (self.process_name.strip(), self.title_contains.strip(), self.title_regex.strip())
        ):
            raise ValueError("a window matcher needs a process name, title text, or title regex")
        if self.title_regex:
            try:
                re.compile(self.title_regex, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid title regex: {exc}") from exc

    def score(self, window: WindowIdentity) -> int:
        """Return 0 for no match, otherwise a specificity score."""
        score = 0
        if self.process_name:
            expected = self.process_name.casefold().removesuffix(".exe")
            actual = window.process_name.casefold().removesuffix(".exe")
            if actual != expected:
                return 0
            score += 100
        if self.title_contains:
            needle = self.title_contains.casefold()
            if needle not in window.title.casefold():
                return 0
            score += 20 + min(len(needle), 50)
        if self.title_regex:
            if re.search(self.title_regex, window.title, re.IGNORECASE) is None:
                return 0
            score += 40
        return score


@dataclass(frozen=True, slots=True)
class WorkspacePlacement:
    id: str
    name: str
    matcher: WindowMatcher
    rect: NormalizedRect
    monitor_index: int = 0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("placement id cannot be empty")
        if not self.name.strip():
            raise ValueError("placement name cannot be empty")
        if self.monitor_index < 0:
            raise ValueError("monitor index cannot be negative")


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    placements: tuple[WorkspacePlacement, ...]
    shortcut: str = ""

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("workspace id cannot be empty")
        if not self.name.strip():
            raise ValueError("workspace name cannot be empty")
        ids = [placement.id for placement in self.placements]
        if len(ids) != len(set(ids)):
            raise ValueError("placement ids must be unique within a workspace")


@dataclass(frozen=True, slots=True)
class PlannedMove:
    placement_id: str
    handle: object
    rect: Rect


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    moves: tuple[PlannedMove, ...]
    unmatched_placements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchedWindow:
    placement_id: str
    handle: object


@dataclass(frozen=True, slots=True)
class WorkspaceMatches:
    matches: tuple[MatchedWindow, ...]
    unmatched_placements: tuple[str, ...]


def match_workspace_windows(
    placements: tuple[WorkspacePlacement, ...], windows: list[WindowIdentity]
) -> WorkspaceMatches:
    """Match rules one-to-one without applying any geometry."""
    unique_windows: dict[object, WindowIdentity] = {}
    for window in windows:
        unique_windows.setdefault(window.handle, window)
    windows = list(unique_windows.values())
    window_keys = [
        (window.process_name.casefold().removesuffix(".exe"), window.title.casefold())
        for window in windows
    ]

    candidates: list[list[int]] = []
    for placement in placements:
        matcher = placement.matcher
        process = (
            matcher.process_name.casefold().removesuffix(".exe") if matcher.process_name else None
        )
        title = matcher.title_contains.casefold() if matcher.title_contains else None
        regex = re.compile(matcher.title_regex, re.IGNORECASE) if matcher.title_regex else None
        matches: list[int] = []
        for index, (window_process, window_title) in enumerate(window_keys):
            if process is not None and process != window_process:
                continue
            if title is not None and title not in window_title:
                continue
            if regex is not None and regex.search(windows[index].title) is None:
                continue
            matches.append(index)
        candidates.append(matches)

    owners: dict[int, int] = {}

    def assign(placement_index: int, seen: set[int]) -> bool:
        for window_index in candidates[placement_index]:
            if window_index not in owners:
                owners[window_index] = placement_index
                return True
        for window_index in candidates[placement_index]:
            if window_index in seen:
                continue
            seen.add(window_index)
            if assign(owners[window_index], seen):
                owners[window_index] = placement_index
                return True
        return False

    for placement_index in sorted(range(len(placements)), key=lambda i: len(candidates[i])):
        assign(placement_index, set())

    assigned = {
        placement_index: windows[window_index].handle
        for window_index, placement_index in owners.items()
    }
    return WorkspaceMatches(
        tuple(
            MatchedWindow(placement.id, assigned[index])
            for index, placement in enumerate(placements)
            if index in assigned
        ),
        tuple(placement.id for index, placement in enumerate(placements) if index not in assigned),
    )


def plan_workspace(
    workspace: Workspace,
    windows: list[WindowIdentity],
    work_areas: list[Rect],
) -> WorkspacePlan:
    """Match each placement to at most one window, deterministically.

    Rules with fewer candidate windows take priority. Ties keep placement
    order; candidate ties keep OS enumeration order. A window can never be
    assigned twice, and overlapping rules can be reassigned to avoid misses.
    """
    eligible = tuple(
        placement for placement in workspace.placements if placement.monitor_index < len(work_areas)
    )
    match_result = match_workspace_windows(eligible, windows)
    matched_by_id = {match.placement_id: match.handle for match in match_result.matches}
    moves: list[PlannedMove] = []
    unmatched: list[str] = []
    for placement in workspace.placements:
        window_handle = matched_by_id.get(placement.id)
        if window_handle is None:
            unmatched.append(placement.id)
            continue
        moves.append(
            PlannedMove(
                placement.id,
                window_handle,
                placement.rect.to_rect(work_areas[placement.monitor_index]),
            )
        )
    return WorkspacePlan(tuple(moves), tuple(unmatched))
