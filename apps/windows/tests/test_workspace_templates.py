"""Tests for ready-to-edit application workspace templates."""

import pytest
from windows_rectangle.core.workspace_templates import (
    office_workspace,
    runescape_workspace,
)
from windows_rectangle.core.workspaces import NormalizedRect, WindowIdentity


def test_office_template_matches_requested_layout():
    workspace = office_workspace()
    assert [placement.name for placement in workspace.placements] == [
        "Slack",
        "Outlook",
        "Chrome",
    ]
    assert workspace.placements[0].rect == NormalizedRect(0, 0, 5000, 5000)
    assert workspace.placements[1].rect == NormalizedRect(0, 5000, 5000, 10000)
    assert workspace.placements[2].rect == NormalizedRect(5000, 0, 10000, 10000)


def test_runescape_template_uses_account_titles_and_balanced_grid():
    workspace = runescape_workspace(["Main", "Skiller", "Iron", "Alt"])
    assert len(workspace.placements) == 4
    assert workspace.placements[0].rect == NormalizedRect(0, 0, 5000, 5000)
    assert workspace.placements[3].rect == NormalizedRect(5000, 5000, 10000, 10000)
    assert (
        workspace.placements[2].matcher.score(WindowIdentity(3, "Iron - RuneLite", "runelite.exe"))
        > 0
    )


def test_runescape_template_validates_account_names():
    with pytest.raises(ValueError, match="at least one"):
        runescape_workspace([])
    with pytest.raises(ValueError, match="unique"):
        runescape_workspace(["Main", "main"])
