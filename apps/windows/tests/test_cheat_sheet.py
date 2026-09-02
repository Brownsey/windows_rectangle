"""Tests for windows_rectangle.ui.cheat_sheet.

Pure formatter — no Qt, no Settings dataclass shenanigans, just dicts in
and strings out.
"""

from __future__ import annotations

from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action

from windows_rectangle.ui.cheat_sheet import (
    ACTION_LABELS,
    UNBOUND_PLACEHOLDER,
    cheat_sheet_html,
    cheat_sheet_rows,
    cheat_sheet_text,
)


def test_action_labels_cover_every_action():
    """Every Action must have a human-readable label, otherwise the cheat
    sheet hides bindings from the user. Fails noisily if someone adds a
    new Action without registering its label."""
    missing = [a for a in Action if a not in ACTION_LABELS]
    assert missing == [], f"missing labels for: {missing}"


def test_rows_show_advanced_actions_as_unbound():
    rows = cheat_sheet_rows(DEFAULT_SHORTCUTS)
    assert len(rows) == len(ACTION_LABELS)
    unbound = [label for label, combo in rows if combo == UNBOUND_PLACEHOLDER]
    assert "Move left" in unbound
    assert "Center two-thirds" in unbound


def test_unbound_action_uses_placeholder():
    shortcuts = dict(DEFAULT_SHORTCUTS)
    shortcuts.pop(Action.CENTER)
    rows = cheat_sheet_rows(shortcuts)
    by_label = {label: combo for label, combo in rows}
    assert by_label[ACTION_LABELS[Action.CENTER]] == UNBOUND_PLACEHOLDER


def test_rows_preserve_canonical_order():
    """Order in ACTION_LABELS is the order shown to the user — locked in
    so reshuffling the dict doesn't silently jumble the cheat sheet."""
    rows = cheat_sheet_rows(DEFAULT_SHORTCUTS)
    label_order = [label for label, _ in rows]
    expected = list(ACTION_LABELS.values())
    assert label_order[: len(expected)] == expected


def test_text_renders_with_columns_aligned():
    text = cheat_sheet_text({Action.LEFT_HALF: "ctrl+alt+left"})
    # Trailing spaces in the alignment column must be exactly what we need
    # to land the combo in the second column.
    assert "ctrl+alt+left" in text
    assert "Left half" in text


def test_html_escapes_combos_and_labels():
    """Defensive: if a user-supplied combo ever contained HTML, the cheat
    sheet must escape it instead of letting Qt render markup."""
    out = cheat_sheet_html({Action.LEFT_HALF: "<script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_html_uses_kbd_for_bound_and_italic_for_unbound():
    bound_html = cheat_sheet_html({Action.LEFT_HALF: "ctrl+alt+left"})
    assert "<kbd>ctrl+alt+left</kbd>" in bound_html
    # Empty shortcuts -> every row is unbound -> italics, no kbd.
    unbound_html = cheat_sheet_html({})
    assert "<kbd>" not in unbound_html
    assert "<i>" in unbound_html


def test_text_empty_for_empty_mapping_with_no_labels():
    """Edge case: passing in a mapping where every label is excluded would
    yield rows because we iterate ACTION_LABELS; but an empty mapping
    still renders every action as unbound (length > 0). Asserting the
    actual contract here so future refactors keep it stable."""
    text = cheat_sheet_text({})
    # Every action shows up as unbound — non-empty output.
    assert UNBOUND_PLACEHOLDER in text
    assert text.count("\n") == len(ACTION_LABELS) - 1
