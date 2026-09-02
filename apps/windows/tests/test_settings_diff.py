"""Tests for windows_rectangle.settings_diff — the pure formatter that
backs `--import-config --dry-run`.

Pure data-in / data-out: takes two Settings, returns a list of
human-readable change lines.
"""

from __future__ import annotations

from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.ports.config_store import Settings

from windows_rectangle.settings_diff import diff_settings


def test_identical_settings_has_no_changes():
    assert diff_settings(Settings(), Settings()) == []


def test_scalar_field_change_surfaces():
    current = Settings(gap=4)
    incoming = Settings(gap=12)
    lines = diff_settings(current, incoming)
    assert any("gap" in ln and "4" in ln and "12" in ln for ln in lines)


def test_multiple_scalar_changes_each_get_a_line():
    current = Settings(gap=0, launch_at_login=False)
    incoming = Settings(gap=8, launch_at_login=True)
    lines = diff_settings(current, incoming)
    assert sum("gap" in ln for ln in lines) == 1
    assert sum("launch_at_login" in ln for ln in lines) == 1


def test_unchanged_scalar_does_not_appear():
    current = Settings(gap=4, launch_at_login=True)
    incoming = Settings(gap=4, launch_at_login=True)
    lines = diff_settings(current, incoming)
    assert not any("gap" in ln for ln in lines)


def test_shortcut_rebind_shows_per_action():
    current = Settings()
    incoming = Settings()
    incoming.shortcuts[Action.LEFT_HALF] = "ctrl+alt+shift+left"
    lines = diff_settings(current, incoming)
    matches = [ln for ln in lines if "left_half" in ln]
    assert len(matches) == 1
    line = matches[0]
    assert DEFAULT_SHORTCUTS[Action.LEFT_HALF] in line
    assert "ctrl+alt+shift+left" in line


def test_cleared_shortcut_renders_as_unbound():
    """User clears an action in the incoming snapshot; diff must show
    the bound-to-unbound transition rather than dropping the line."""
    current = Settings()
    incoming = Settings()
    incoming.shortcuts.pop(Action.CENTER)
    lines = diff_settings(current, incoming)
    matches = [ln for ln in lines if "center" in ln and "(unbound)" in ln]
    assert matches, "cleared shortcut should appear with (unbound) marker"


def test_newly_bound_shortcut_surfaces():
    """Conversely: action was unbound, incoming binds it."""
    current = Settings()
    current.shortcuts.pop(Action.CENTER)
    incoming = Settings()  # has the default
    lines = diff_settings(current, incoming)
    matches = [ln for ln in lines if "center" in ln]
    assert matches
    line = matches[0]
    assert "(unbound)" in line
    assert DEFAULT_SHORTCUTS[Action.CENTER] in line


def test_change_format_includes_field_name():
    """Locked-in format so users can grep / pipe the output."""
    current = Settings(gap=4)
    incoming = Settings(gap=12)
    lines = diff_settings(current, incoming)
    line = next(ln for ln in lines if "gap" in ln)
    # `field: current -> incoming`
    assert line.strip().startswith("gap:")
    assert "->" in line
