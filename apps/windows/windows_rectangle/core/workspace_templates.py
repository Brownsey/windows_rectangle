"""Ready-to-edit workspace templates for common application setups."""

from __future__ import annotations

import math

from .workspace_presets import preset_rect
from .workspaces import (
    BASIS,
    NormalizedRect,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
    new_id,
)


def office_workspace(name: str = "Office focus") -> Workspace:
    """Slack top-left, Outlook bottom-left, and Chrome on the right."""
    rules = (
        ("Slack", "slack.exe", "top_left"),
        ("Outlook", "outlook.exe", "bottom_left"),
        ("Chrome", "chrome.exe", "right_half"),
    )
    return Workspace(
        new_id(),
        name.strip() or "Office focus",
        tuple(
            WorkspacePlacement(
                new_id(),
                label,
                WindowMatcher(process_name=process),
                preset_rect(position),
            )
            for label, process, position in rules
        ),
    )


def runescape_workspace(
    accounts: list[str] | tuple[str, ...],
    name: str = "RuneScape accounts",
    *,
    process_name: str = "RuneLite.exe",
    monitor_index: int = 0,
) -> Workspace:
    """Create stable title-specific account rules in a balanced monitor grid."""
    clean = tuple(account.strip() for account in accounts if account.strip())
    if not clean:
        raise ValueError("enter at least one RuneScape account name")
    if len({account.casefold() for account in clean}) != len(clean):
        raise ValueError("RuneScape account names must be unique")
    columns = math.ceil(math.sqrt(len(clean)))
    rows = math.ceil(len(clean) / columns)
    placements: list[WorkspacePlacement] = []
    for index, account in enumerate(clean):
        column, row = index % columns, index // columns
        rect = NormalizedRect(
            round(column * BASIS / columns),
            round(row * BASIS / rows),
            round((column + 1) * BASIS / columns),
            round((row + 1) * BASIS / rows),
        )
        placements.append(
            WorkspacePlacement(
                new_id(),
                account,
                WindowMatcher(process_name=process_name, title_contains=account),
                rect,
                monitor_index,
            )
        )
    return Workspace(new_id(), name.strip() or "RuneScape accounts", tuple(placements))
