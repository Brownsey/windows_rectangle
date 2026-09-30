"""Tests for named multi-window workspace planning."""

from itertools import product

import pytest

from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowIdentity,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
    match_workspace_windows,
    plan_workspace,
)


def placement(id_: str, title: str, rect: NormalizedRect, monitor: int = 0):
    return WorkspacePlacement(
        id_, title, WindowMatcher(process_name="runelite.exe", title_contains=title), rect, monitor
    )


def test_normalized_rect_scales_and_preserves_shared_boundaries():
    work = Rect(100, 50, 1919, 1079)
    left = NormalizedRect(0, 0, 5000, 10000).to_rect(work)
    right = NormalizedRect(5000, 0, 10000, 10000).to_rect(work)
    assert left.right == right.left
    assert left.left == work.left
    assert right.right == work.right


def test_capture_round_trip_is_within_one_pixel():
    work = Rect(-1920, 0, 1920, 1040)
    original = Rect(-1900, 20, 900, 500)
    restored = NormalizedRect.from_rect(original, work).to_rect(work)
    assert abs(restored.x - original.x) <= 1
    assert abs(restored.y - original.y) <= 1
    assert abs(restored.width - original.width) <= 1
    assert abs(restored.height - original.height) <= 1


@pytest.mark.parametrize(
    "values",
    [(-1, 0, 1, 1), (0, 0, 0, 1), (0, 5, 10_001, 10), (0, 5, 10, 5)],
)
def test_invalid_normalized_rect_is_rejected(values):
    with pytest.raises(ValueError):
        NormalizedRect(*values)


def test_matcher_combines_process_and_account_title_case_insensitively():
    matcher = WindowMatcher(process_name="RuneLite.exe", title_contains="Alice")
    assert matcher.score(WindowIdentity(1, "Alice - RuneLite", "runelite")) > 0
    assert matcher.score(WindowIdentity(2, "Bob - RuneLite", "runelite.exe")) == 0
    assert matcher.score(WindowIdentity(3, "Alice - RuneLite", "chrome.exe")) == 0


def test_match_workspace_windows_is_geometry_independent_and_one_to_one():
    placements = (
        placement("alice", "Alice", NormalizedRect(0, 0, 5000, 10000), monitor=9),
        placement("bob", "Bob", NormalizedRect(5000, 0, 10000, 10000)),
    )
    result = match_workspace_windows(
        placements,
        [WindowIdentity(1, "Alice - RuneLite", "runelite.exe")],
    )
    assert [(match.placement_id, match.handle) for match in result.matches] == [("alice", 1)]
    assert result.unmatched_placements == ("bob",)


def test_specific_rule_claims_its_window_before_earlier_broad_rule():
    rect = NormalizedRect(0, 0, 5000, 5000)
    placements = (
        WorkspacePlacement("broad", "Any browser", WindowMatcher(process_name="chrome.exe"), rect),
        WorkspacePlacement(
            "specific",
            "Inbox",
            WindowMatcher(process_name="chrome.exe", title_contains="Inbox"),
            rect,
        ),
    )
    windows = [WindowIdentity(1, "Inbox", "chrome.exe"), WindowIdentity(2, "Docs", "chrome.exe")]
    result = match_workspace_windows(placements, windows)
    assert [(m.placement_id, m.handle) for m in result.matches] == [("broad", 2), ("specific", 1)]


def test_regex_overlap_keeps_the_only_window_for_an_exact_title():
    rect = NormalizedRect(0, 0, 5000, 5000)
    placements = (
        WorkspacePlacement(
            "regex", "Either", WindowMatcher(process_name="app", title_regex=r"Window [12]"), rect
        ),
        WorkspacePlacement(
            "exact", "First", WindowMatcher(process_name="app", title_contains="Window 1"), rect
        ),
    )
    windows = [WindowIdentity(1, "Window 1", "app"), WindowIdentity(2, "Window 2", "app")]

    result = match_workspace_windows(placements, windows)

    assert [(match.placement_id, match.handle) for match in result.matches] == [
        ("regex", 2),
        ("exact", 1),
    ]
    assert result.unmatched_placements == ()


def test_overlapping_equal_size_rules_find_all_possible_windows():
    rect = NormalizedRect(0, 0, 5000, 5000)
    placements = tuple(
        WorkspacePlacement(name, name, WindowMatcher(title_regex=pattern), rect)
        for name, pattern in (
            ("first", r"Window [12]"),
            ("second", r"Window [23]"),
            ("third", r"Window [12]"),
        )
    )
    windows = [WindowIdentity(i, f"Window {i}", "app") for i in (1, 2, 3)]

    result = match_workspace_windows(placements, windows)

    assert len(result.matches) == 3
    assert len({match.handle for match in result.matches}) == 3
    assert result.unmatched_placements == ()


def test_duplicate_window_handle_is_only_assigned_once():
    rect = NormalizedRect(0, 0, 5000, 5000)
    placements = (
        WorkspacePlacement("first", "First", WindowMatcher(title_contains="Window"), rect),
        WorkspacePlacement("second", "Second", WindowMatcher(title_contains="Window"), rect),
    )
    windows = [WindowIdentity(1, "Window", "app"), WindowIdentity(1, "Window", "app")]

    result = match_workspace_windows(placements, windows)

    assert [(match.placement_id, match.handle) for match in result.matches] == [("first", 1)]
    assert result.unmatched_placements == ("second",)


def test_matching_preserves_casefold_exe_suffix_regex_and_window_order():
    rect = NormalizedRect(0, 0, 5000, 5000)
    placements = (
        WorkspacePlacement(
            "unicode",
            "Unicode",
            WindowMatcher(process_name="CHROME.EXE", title_contains="straße", title_regex=r"tÄb$"),
            rect,
        ),
        WorkspacePlacement("first", "First", WindowMatcher(title_regex=r"Window [12]"), rect),
        WorkspacePlacement("second", "Second", WindowMatcher(title_regex=r"Window [12]"), rect),
    )
    windows = [
        WindowIdentity(10, "STRASSE TäB", "chrome"),
        WindowIdentity(1, "Window 1", "app"),
        WindowIdentity(2, "Window 2", "app"),
    ]

    result = match_workspace_windows(placements, windows)

    assert [(match.placement_id, match.handle) for match in result.matches] == [
        ("unicode", 10),
        ("first", 1),
        ("second", 2),
    ]


def test_small_overlap_cases_reach_maximum_cardinality():
    windows = [WindowIdentity(i, f"Window {i}", "app") for i in (1, 2, 3)]
    rules = (
        WindowMatcher(title_regex=r"Window [12]"),
        WindowMatcher(title_regex=r"Window [23]"),
        WindowMatcher(title_contains="Window 1"),
        WindowMatcher(process_name="APP.EXE"),
    )
    rect = NormalizedRect(0, 0, 5000, 5000)
    for matchers in product(rules, repeat=3):
        placements = tuple(
            WorkspacePlacement(str(index), str(index), matcher, rect)
            for index, matcher in enumerate(matchers)
        )
        candidates = [
            {index for index, window in enumerate(windows) if matcher.score(window)}
            for matcher in matchers
        ]
        possible = (
            choice
            for choice in product((None, 0, 1, 2), repeat=3)
            if all(index is None or index in candidates[p] for p, index in enumerate(choice))
        )
        maximum = max(
            sum(index is not None for index in choice)
            for choice in possible
            if len({index for index in choice if index is not None})
            == sum(index is not None for index in choice)
        )

        result = match_workspace_windows(placements, windows)

        assert len(result.matches) == maximum, matchers
        assert len({match.handle for match in result.matches}) == len(result.matches)
        assert all(
            match.handle - 1 in candidates[int(match.placement_id)] for match in result.matches
        )


def test_invalid_regex_and_empty_matcher_are_rejected():
    with pytest.raises(ValueError):
        WindowMatcher()
    with pytest.raises(ValueError):
        WindowMatcher(title_regex="[")


def test_plan_assigns_each_window_once_and_reports_missing():
    workspace = Workspace(
        "gaming",
        "RuneScape",
        (
            placement("alice", "Alice", NormalizedRect(0, 0, 5000, 10000)),
            placement("bob", "Bob", NormalizedRect(5000, 0, 10000, 10000)),
            placement("carol", "Carol", NormalizedRect(0, 0, 10000, 10000)),
        ),
    )
    windows = [
        WindowIdentity(11, "Bob - RuneLite", "RuneLite.exe"),
        WindowIdentity(10, "Alice - RuneLite", "runelite.exe"),
    ]
    plan = plan_workspace(workspace, windows, [Rect(0, 0, 1920, 1080)])
    assert [(move.placement_id, move.handle) for move in plan.moves] == [
        ("alice", 10),
        ("bob", 11),
    ]
    assert plan.unmatched_placements == ("carol",)


def test_plan_handles_missing_monitor_without_crashing():
    workspace = Workspace(
        "office",
        "Office",
        (placement("slack", "Slack", NormalizedRect(0, 0, 5000, 5000), monitor=2),),
    )
    plan = plan_workspace(
        workspace,
        [WindowIdentity(1, "Slack", "client.exe")],
        [Rect(0, 0, 1920, 1080)],
    )
    assert plan.moves == ()
    assert plan.unmatched_placements == ("slack",)
