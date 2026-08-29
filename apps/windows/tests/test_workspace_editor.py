"""Tests for the pure workspace editor/review controller."""

import pytest
from windows_rectangle.core.actions import Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowIdentity,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
)
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui.workspace_editor import WorkspaceEditorController


def workspace(shortcut=""):
    return Workspace(
        "office",
        "Office",
        (
            WorkspacePlacement(
                "slack",
                "Slack",
                WindowMatcher(process_name="slack.exe", title_contains="Slack"),
                NormalizedRect(0, 0, 5000, 5000),
            ),
        ),
        shortcut,
    )


class Manager:
    def list_windows(self):
        return [WindowIdentity(1, "Slack", "slack.exe")]

    def list_work_areas(self):
        return [Rect(0, 0, 1920, 1080)]

    def get_window_rect(self, _handle):
        return Rect(0, 0, 960, 540)

    def monitor_index_for_window(self, _handle):
        return 0

    def is_maximized(self, _handle):
        return False

    def restore_window(self, _handle):
        pass

    def set_window_rect(self, _handle, _rect):
        return True


def test_capture_edit_match_and_commit():
    controller = WorkspaceEditorController(Settings())
    captured = controller.capture(Manager(), "Office")
    controller.rename(captured.id, "Daily work")
    controller.set_shortcut(captured.id, "ctrl+alt+1")
    placement = controller.get(captured.id).placements[0]
    controller.update_placement(
        captured.id,
        placement.id,
        name="Team chat",
        process_name="slack.exe",
        title_contains="Slack",
        title_regex="",
        monitor_index=0,
    )
    assert controller.match_counts(Manager(), captured.id) == (1, 0)
    saved = []
    report = controller.commit(saved.append)
    assert report.ok
    assert saved[0].workspaces[0].name == "Daily work"
    assert saved[0].workspaces[0].shortcut == "ctrl+alt+1"
    assert not controller.is_dirty


def test_duplicate_name_and_shortcut_conflicts_block_commit():
    first = workspace("ctrl+alt+1")
    second = Workspace("other", "office", (), "ctrl+alt+1")
    controller = WorkspaceEditorController(Settings(workspaces=(first, second)))
    report = controller.validate()
    assert not report.ok
    assert any("Duplicate workspace name" in error for error in report.errors)
    assert any("shortcut already used" in error for error in report.errors)


def test_action_shortcut_conflict_is_reported():
    settings = Settings(workspaces=(workspace("ctrl+alt+left"),))
    settings.shortcuts[Action.LEFT_HALF] = "ctrl+alt+left"
    report = WorkspaceEditorController(settings).validate()
    assert any("left_half" in error for error in report.errors)


def test_broad_and_duplicate_rules_warn():
    broad = WorkspacePlacement(
        "one",
        "One",
        WindowMatcher(process_name="chrome.exe"),
        NormalizedRect(0, 0, 5000, 10000),
    )
    duplicate = WorkspacePlacement(
        "two",
        "Two",
        WindowMatcher(process_name="chrome.exe"),
        NormalizedRect(5000, 0, 10000, 10000),
    )
    controller = WorkspaceEditorController(
        Settings(workspaces=(Workspace("web", "Web", (broad, duplicate)),))
    )
    report = controller.validate()
    assert report.ok
    assert len(report.warnings) == 3


def test_invalid_matcher_edit_does_not_corrupt_staged_state():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    with pytest.raises(ValueError):
        controller.update_placement(
            "office",
            "slack",
            name="Slack",
            process_name="",
            title_contains="",
            title_regex="",
            monitor_index=0,
        )
    assert controller.get("office").placements[0].matcher.process_name == "slack.exe"


def test_delete_active_workspace_selects_next():
    controller = WorkspaceEditorController(
        Settings(
            workspaces=(workspace(), Workspace("gaming", "Gaming", ())),
            active_workspace_id="office",
        )
    )
    controller.delete_workspace("office")
    assert controller.staged.active_workspace_id == "gaming"
