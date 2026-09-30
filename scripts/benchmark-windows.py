"""Repeatable workspace matcher comparison: python scripts/benchmark-windows.py."""

from __future__ import annotations

import statistics
import sys
from functools import partial
from pathlib import Path
from random import Random
from time import process_time
from timeit import repeat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "windows"))

from windows_rectangle.core.workspaces import (  # noqa: E402
    MatchedWindow,
    NormalizedRect,
    WindowIdentity,
    WindowMatcher,
    WorkspaceMatches,
    WorkspacePlacement,
    match_workspace_windows,
)


def previous_matcher(
    placements: tuple[WorkspacePlacement, ...], windows: list[WindowIdentity]
) -> WorkspaceMatches:
    """Matcher before the linear scan change, retained as a timing baseline."""
    available = list(windows)
    matches: list[MatchedWindow] = []
    unmatched: list[str] = []
    for placement in placements:
        ranked = sorted(
            enumerate(available),
            key=lambda item: (-placement.matcher.score(item[1]), item[0]),
        )
        if not ranked or placement.matcher.score(ranked[0][1]) == 0:
            unmatched.append(placement.id)
            continue
        index, window = ranked[0]
        available.pop(index)
        matches.append(MatchedWindow(placement.id, window.handle))
    return WorkspaceMatches(tuple(matches), tuple(unmatched))


def corrected_baseline(
    placements: tuple[WorkspacePlacement, ...], windows: list[WindowIdentity]
) -> WorkspaceMatches:
    """Frozen maximum-cardinality matcher before normalization optimization."""
    unique_windows: dict[object, WindowIdentity] = {}
    for window in windows:
        unique_windows.setdefault(window.handle, window)
    windows = list(unique_windows.values())

    candidates: list[list[int]] = []
    for placement in placements:
        scores = [placement.matcher.score(window) for window in windows]
        candidates.append(
            sorted((index for index, score in enumerate(scores) if score), key=lambda i: -scores[i])
        )

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


def unique_case(
    count: int, available: int
) -> tuple[tuple[WorkspacePlacement, ...], list[WindowIdentity]]:
    rect = NormalizedRect(0, 0, 10000, 10000)
    placements = tuple(
        WorkspacePlacement(
            str(i),
            f"Window {i:03d}",
            WindowMatcher(process_name="chrome.exe", title_contains=f"Window {i:03d}"),
            rect,
        )
        for i in range(count)
    )
    windows = [WindowIdentity(i, f"Window {i:03d}", "chrome.exe") for i in range(available)]
    Random(0).shuffle(windows)
    return placements, windows


if __name__ == "__main__":
    rect = NormalizedRect(0, 0, 10000, 10000)
    overlap = (
        tuple(
            WorkspacePlacement(name, name, WindowMatcher(title_regex=pattern), rect)
            for name, pattern in (
                ("first", r"Window [12]"),
                ("second", r"Window [23]"),
                ("third", r"Window [12]"),
            )
        ),
        [WindowIdentity(i, f"Window {i}", "chrome.exe") for i in (1, 2, 3)],
    )
    cases = (
        ("unique-10", *unique_case(10, 10)),
        ("unique-100", *unique_case(100, 100)),
        ("overlap", *overlap),
        ("missing", *unique_case(10, 8)),
    )
    for case_name, placements, windows in cases:
        expected = corrected_baseline(placements, windows)
        assert match_workspace_windows(placements, windows) == expected, case_name
        if case_name.startswith("unique"):
            assert previous_matcher(placements, windows) == expected, case_name
        runs = {"unique-10": 2_000, "unique-100": 50, "overlap": 5_000, "missing": 2_000}[case_name]
        for label, matcher in (
            ("baseline", corrected_baseline),
            ("current", match_workspace_windows),
        ):
            times = repeat(
                partial(matcher, placements, windows), timer=process_time, number=runs, repeat=5
            )
            milliseconds = statistics.median(times) * 1000 / runs
            print(f"{case_name} {label}: {milliseconds:.3f}ms CPU/run ({runs} runs)")
