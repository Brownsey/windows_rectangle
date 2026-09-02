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


def test_create_manual_application_rule_and_change_position():
    controller = WorkspaceEditorController(Settings())
    created = controller.create("RuneScape accounts")
    placement = controller.add_placement(
        created.id,
        name="Account - Stephen",
        process_name="RuneLite.exe",
        title_contains="Stephen",
        preset_id="top_left",
    )
    assert placement.rect == NormalizedRect(0, 0, 5000, 5000)
    assert placement.matcher.score(WindowIdentity(1, "Stephen", "runelite.exe")) > 0

    controller.set_placement_preset(created.id, placement.id, "right_half")
    assert controller.get(created.id).placements[0].rect == NormalizedRect(5000, 0, 10000, 10000)


def test_manual_application_rule_keeps_launch_command():
    controller = WorkspaceEditorController(Settings())
    created = controller.create("RuneScape accounts")

    placement = controller.add_placement(
        created.id,
        name="Alice",
        process_name="runelite.exe",
        title_contains="Alice",
        launch_command=r"C:\RuneLite\RuneLite.exe --profile Alice",
    )

    assert placement.launch_command == r"C:\RuneLite\RuneLite.exe --profile Alice"


def test_unchanged_application_edit_is_allowed_before_position_change():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    original = controller.get("office").placements[0]

    controller.update_placement(
        "office",
        original.id,
        name=original.name,
        process_name=original.matcher.process_name,
        title_contains=original.matcher.title_contains,
        title_regex=original.matcher.title_regex,
        monitor_index=original.monitor_index,
    )
    controller.set_placement_preset("office", original.id, "right_half")

    assert controller.get("office").placements[0].rect == NormalizedRect(5000, 0, 10000, 10000)


def test_layout_edits_rebase_onto_newer_general_settings():
    controller = WorkspaceEditorController(Settings(gap=4, workspaces=(workspace(),)))
    controller.rename("office", "Updated office")
    captured = Workspace("captured", "Captured from tray", ())

    controller.rebase_onto(Settings(gap=24, workspaces=(workspace(), captured)))

    assert controller.staged.gap == 24
    assert controller.get("office").name == "Updated office"
    assert controller.get("captured").name == "Captured from tray"


def test_manual_rule_requires_a_match_signal():
    controller = WorkspaceEditorController(Settings())
    created = controller.create("Empty")
    with pytest.raises(ValueError, match="matcher"):
        controller.add_placement(created.id, name="Unknown")


def test_custom_normalized_rect_can_be_staged():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    custom = NormalizedRect(1250, 2500, 8750, 9000)
    controller.set_placement_rect("office", "slack", custom)
    assert controller.get("office").placements[0].rect == custom


def test_templates_duplicate_and_per_rule_match_results():
    controller = WorkspaceEditorController(Settings())
    gaming = controller.add_runescape_template(["Main", "Iron"])
    assert len(gaming.placements) == 2
    duplicate = controller.duplicate(gaming.id)
    assert duplicate.name == "RuneScape accounts copy"
    assert duplicate.id != gaming.id
    assert {item.id for item in duplicate.placements}.isdisjoint(
        item.id for item in gaming.placements
    )

    office = controller.add_office_template()
    results = controller.match_results(Manager(), office.id)
    assert list(results.values()) == [True, False, False]


def test_record_current_positions_learns_exact_rect_and_monitor():
    class LiveManager(Manager):
        def list_work_areas(self):
            return [Rect(0, 0, 1920, 1080), Rect(1920, 0, 2560, 1440)]

        def get_window_rect(self, _handle):
            return Rect(2560, 144, 1280, 1008)

        def monitor_index_for_window(self, _handle):
            return 1

    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    result = controller.record_current_positions(LiveManager(), "office")
    recorded = controller.get("office").placements[0]
    assert result.updated == 1
    assert result.not_found == ()
    assert recorded.monitor_index == 1
    assert recorded.rect == NormalizedRect(2500, 1000, 7500, 8000)


def test_record_current_positions_preserves_missing_rules():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    manager = Manager()
    manager.list_windows = lambda: []
    result = controller.record_current_positions(manager, "office")
    assert result.updated == 0
    assert result.not_found == ("slack",)
    assert controller.get("office") == workspace()


def test_autosave_persists_applies_and_clears_dirty_state():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    controller.rename("office", "Saved automatically")
    saved = []
    applied = []
    outcome = controller.autosave(saved.append, applied.append)
    assert outcome.saved
    assert saved[0].workspaces[0].name == "Saved automatically"
    assert applied[0].workspaces[0].name == "Saved automatically"
    assert not controller.is_dirty


def test_autosave_failure_is_visible_and_keeps_retryable_state():
    controller = WorkspaceEditorController(Settings(workspaces=(workspace(),)))
    controller.rename("office", "Still dirty")

    def fail(_settings):
        raise OSError("disk full")

    outcome = controller.autosave(fail)
    assert not outcome.saved
    assert outcome.error == "disk full"
    assert controller.is_dirty


def test_autosave_does_not_write_invalid_settings():
    controller = WorkspaceEditorController(
        Settings(workspaces=(workspace("ctrl+alt+1"), Workspace("two", "Office", ())))
    )
    saved = []
    outcome = controller.autosave(saved.append)
    assert not outcome.saved
    assert outcome.validation.errors
    assert saved == []
