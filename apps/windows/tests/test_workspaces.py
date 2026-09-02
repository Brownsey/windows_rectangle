"""Tests for named multi-window workspace planning."""

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


def test_specific_workspace_rule_wins_before_broad_rule():
    rect = NormalizedRect(0, 0, 5000, 10000)
    placements = (
        WorkspacePlacement("broad", "Any Chrome", WindowMatcher(process_name="chrome"), rect),
        WorkspacePlacement(
            "mail",
            "Mail",
            WindowMatcher(process_name="chrome", title_contains="Mail"),
            rect,
        ),
    )
    windows = [
        WindowIdentity(1, "Mail - Chrome", "chrome.exe"),
        WindowIdentity(2, "Docs - Chrome", "chrome.exe"),
    ]

    result = match_workspace_windows(placements, windows)

    assert [(match.placement_id, match.handle) for match in result.matches] == [
        ("broad", 2),
        ("mail", 1),
    ]


def test_broad_rule_does_not_take_only_window_matching_specific_rule():
    rect = NormalizedRect(0, 0, 5000, 10000)
    placements = (
        WorkspacePlacement("broad", "Any Chrome", WindowMatcher(process_name="chrome"), rect),
        WorkspacePlacement(
            "mail",
            "Mail",
            WindowMatcher(title_contains="Mail"),
            rect,
        ),
    )

    result = match_workspace_windows(
        placements,
        [WindowIdentity(1, "Mail - Chrome", "chrome.exe")],
    )

    assert [(match.placement_id, match.handle) for match in result.matches] == [("mail", 1)]
    assert result.unmatched_placements == ("broad",)


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
