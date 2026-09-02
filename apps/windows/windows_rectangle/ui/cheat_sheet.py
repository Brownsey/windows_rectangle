"""Cheat-sheet formatting — turn a `Settings.shortcuts` mapping into a
display-ready list of `(label, combo)` rows or a single HTML/plain-text
block for a popup.

Pure, no Qt — so the tray (`ui/tray.py`) can call this on any thread, and
tests can lock in the row order / unbound rendering without spinning up
PySide6.

Used by `ui/tray.py`'s "Cheat sheet…" menu item.
"""

from __future__ import annotations

import html
from collections.abc import Mapping

from ..core.actions import Action

# Human-readable label for each action. Keys are the canonical Action enum
# members; the order here is the order rows appear in the cheat sheet.
ACTION_LABELS: dict[Action, str] = {
    Action.LEFT_HALF: "Left half",
    Action.RIGHT_HALF: "Right half",
    Action.TOP_HALF: "Top half",
    Action.BOTTOM_HALF: "Bottom half",
    Action.TOP_LEFT_QUARTER: "Top-left quarter",
    Action.TOP_RIGHT_QUARTER: "Top-right quarter",
    Action.BOTTOM_LEFT_QUARTER: "Bottom-left quarter",
    Action.BOTTOM_RIGHT_QUARTER: "Bottom-right quarter",
    Action.TOP_LEFT_SIXTH: "Top-left sixth",
    Action.TOP_CENTER_SIXTH: "Top-center sixth",
    Action.TOP_RIGHT_SIXTH: "Top-right sixth",
    Action.BOTTOM_LEFT_SIXTH: "Bottom-left sixth",
    Action.BOTTOM_CENTER_SIXTH: "Bottom-center sixth",
    Action.BOTTOM_RIGHT_SIXTH: "Bottom-right sixth",
    Action.FIRST_THIRD: "First third",
    Action.CENTER_THIRD: "Center third",
    Action.LAST_THIRD: "Last third",
    Action.FIRST_TWO_THIRDS: "First two-thirds",
    Action.LAST_TWO_THIRDS: "Last two-thirds",
    Action.CENTER_HALF: "Center half",
    Action.CENTER_TWO_THIRDS: "Center two-thirds",
    Action.FIRST_FOURTH: "First fourth",
    Action.SECOND_FOURTH: "Second fourth",
    Action.THIRD_FOURTH: "Third fourth",
    Action.LAST_FOURTH: "Last fourth",
    Action.FIRST_THREE_FOURTHS: "First three-fourths",
    Action.CENTER_THREE_FOURTHS: "Center three-fourths",
    Action.LAST_THREE_FOURTHS: "Last three-fourths",
    Action.TOP_LEFT_THIRD: "Top-left two-thirds",
    Action.TOP_RIGHT_THIRD: "Top-right two-thirds",
    Action.BOTTOM_LEFT_THIRD: "Bottom-left two-thirds",
    Action.BOTTOM_RIGHT_THIRD: "Bottom-right two-thirds",
    Action.TOP_VERTICAL_THIRD: "Top vertical third",
    Action.MIDDLE_VERTICAL_THIRD: "Middle vertical third",
    Action.BOTTOM_VERTICAL_THIRD: "Bottom vertical third",
    Action.TOP_VERTICAL_TWO_THIRDS: "Top vertical two-thirds",
    Action.BOTTOM_VERTICAL_TWO_THIRDS: "Bottom vertical two-thirds",
    Action.MAXIMIZE: "Maximize",
    Action.MAXIMIZE_HEIGHT: "Maximize height",
    Action.MAXIMIZE_WIDTH: "Maximize width",
    Action.ALMOST_MAXIMIZE: "Almost maximize",
    Action.CENTER: "Center (no resize)",
    Action.CENTER_PROMINENTLY: "Center prominently",
    Action.LARGER: "Larger",
    Action.SMALLER: "Smaller",
    Action.LARGER_WIDTH: "Larger width",
    Action.SMALLER_WIDTH: "Smaller width",
    Action.LARGER_HEIGHT: "Larger height",
    Action.SMALLER_HEIGHT: "Smaller height",
    Action.MOVE_LEFT: "Move left",
    Action.MOVE_RIGHT: "Move right",
    Action.MOVE_UP: "Move up",
    Action.MOVE_DOWN: "Move down",
    Action.HALVE_HEIGHT_UP: "Halve height upward",
    Action.HALVE_HEIGHT_DOWN: "Halve height downward",
    Action.HALVE_WIDTH_LEFT: "Halve width leftward",
    Action.HALVE_WIDTH_RIGHT: "Halve width rightward",
    Action.DOUBLE_HEIGHT_UP: "Double height upward",
    Action.DOUBLE_HEIGHT_DOWN: "Double height downward",
    Action.DOUBLE_WIDTH_LEFT: "Double width leftward",
    Action.DOUBLE_WIDTH_RIGHT: "Double width rightward",
    Action.RESTORE: "Restore (undo)",
    Action.NEXT_DISPLAY: "Move to next display",
    Action.PREV_DISPLAY: "Move to previous display",
    Action.TOGGLE_ALWAYS_ON_TOP: "Toggle always on top",
    Action.DISPLAY_1: "Move to display 1",
    Action.DISPLAY_2: "Move to display 2",
    Action.DISPLAY_3: "Move to display 3",
    Action.DISPLAY_4: "Move to display 4",
    Action.DISPLAY_5: "Move to display 5",
    Action.DISPLAY_6: "Move to display 6",
    Action.DISPLAY_7: "Move to display 7",
    Action.DISPLAY_8: "Move to display 8",
    Action.DISPLAY_9: "Move to display 9",
}


# Rendering for an action with no shortcut assigned. Centralised so the UI
# and tests agree on the placeholder.
UNBOUND_PLACEHOLDER = "(unbound)"


def cheat_sheet_rows(shortcuts: Mapping[Action, str]) -> list[tuple[str, str]]:
    """Return `(label, combo)` rows in the canonical ACTION_LABELS order.

    Unbound actions (missing from `shortcuts`) render with
    `UNBOUND_PLACEHOLDER` so the user can see *every* available action and
    spot the unbound ones. Any extra keys in `shortcuts` that aren't in
    `ACTION_LABELS` are appended at the bottom for forward-compat.
    """
    rows: list[tuple[str, str]] = []
    for action, label in ACTION_LABELS.items():
        combo = shortcuts.get(action, "")
        rows.append((label, combo if combo else UNBOUND_PLACEHOLDER))
    # Forward-compat: any Action enum value not in ACTION_LABELS (e.g. a
    # future addition someone forgot to register a label for) still gets
    # listed instead of being silently dropped.
    for action, combo in shortcuts.items():
        if action in ACTION_LABELS:
            continue
        rows.append((action.value, combo if combo else UNBOUND_PLACEHOLDER))
    return rows


def cheat_sheet_text(shortcuts: Mapping[Action, str]) -> str:
    """Plain-text two-column rendering. Useful for log dumps and tests."""
    rows = cheat_sheet_rows(shortcuts)
    if not rows:
        return ""
    label_w = max(len(label) for label, _ in rows)
    return "\n".join(f"{label.ljust(label_w)}  {combo}" for label, combo in rows)


def cheat_sheet_html(shortcuts: Mapping[Action, str]) -> str:
    """HTML table — Qt's `QMessageBox.setText` renders this nicely.

    All user-provided strings are escaped, even though the combos come
    from our own parser; defensive against the day someone wires a
    fully user-typed combo string straight in.
    """
    rows = cheat_sheet_rows(shortcuts)
    body_rows: list[str] = []
    for label, combo in rows:
        is_unbound = combo == UNBOUND_PLACEHOLDER
        # Dimmer rendering for unbound rows; <kbd> hint for bound combos.
        if is_unbound:
            combo_cell = f"<i>{html.escape(combo)}</i>"
        else:
            combo_cell = f"<kbd>{html.escape(combo)}</kbd>"
        body_rows.append(f"<tr><td>{html.escape(label)}</td><td>{combo_cell}</td></tr>")
    return (
        "<table cellspacing='6' cellpadding='2'>"
        "<thead><tr><th align='left'>Action</th>"
        "<th align='left'>Shortcut</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )
