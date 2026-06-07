"""Tests for windows_rectangle.ui.preferences.

The PrefsController is pure-Python — no PySide6 / no Win32 needed.
"""

import pytest

from windows_rectangle.core.actions import Action
from windows_rectangle.core.shortcuts import ShortcutParseError
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui.preferences import (
    ALMOST_MAX_MAX,
    ALMOST_MAX_MIN,
    GAP_MAX,
    GAP_MIN,
    PrefsController,
    ValidationReport,
)


def test_baseline_and_staged_start_equal():
    pc = PrefsController(baseline=Settings())
    assert not pc.is_dirty


def test_set_gap_clamps_below_zero():
    # Baseline gap=10 so the clamp-to-zero is detectable as a change.
    pc = PrefsController(baseline=Settings(gap=10))
    pc.set_gap(-5)
    assert pc.staged.gap == GAP_MIN
    assert pc.is_dirty


def test_set_gap_clamps_above_max():
    pc = PrefsController(baseline=Settings())
    pc.set_gap(10_000)
    assert pc.staged.gap == GAP_MAX


def test_set_gap_rejects_non_int():
    pc = PrefsController(baseline=Settings())
    with pytest.raises(TypeError):
        pc.set_gap(7.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        pc.set_gap(True)  # type: ignore[arg-type]


def test_toggles_are_bool_coerced():
    pc = PrefsController(baseline=Settings(drag_to_edge_enabled=True))
    pc.set_drag_to_edge_enabled(0)  # type: ignore[arg-type]
    assert pc.staged.drag_to_edge_enabled is False
    pc.set_launch_at_login(1)  # type: ignore[arg-type]
    assert pc.staged.launch_at_login is True


def test_set_almost_maximize_scale_clamps():
    pc = PrefsController(baseline=Settings())
    pc.set_almost_maximize_scale(2.0)
    assert pc.staged.almost_maximize_scale == ALMOST_MAX_MAX
    pc.set_almost_maximize_scale(-0.5)
    assert pc.staged.almost_maximize_scale == ALMOST_MAX_MIN


def test_set_cycle_idle_timeout_clamps():
    pc = PrefsController(baseline=Settings())
    pc.set_cycle_idle_timeout(-1.0)
    assert pc.staged.cycle_idle_timeout == 0.0
    pc.set_cycle_idle_timeout(999.0)
    assert pc.staged.cycle_idle_timeout == 10.0


def test_set_shortcut_normalises():
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "  Control + ALT + LEFT  ")
    assert pc.staged.shortcuts[Action.LEFT_HALF] == "ctrl+alt+left"


def test_set_shortcut_raises_on_garbage():
    pc = PrefsController(baseline=Settings())
    with pytest.raises(ShortcutParseError):
        pc.set_shortcut(Action.LEFT_HALF, "+++")


def test_clear_shortcut_removes_binding():
    pc = PrefsController(baseline=Settings())
    pc.clear_shortcut(Action.LEFT_HALF)
    assert Action.LEFT_HALF not in pc.staged.shortcuts


def test_shortcut_conflicts_detects_duplicates():
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+alt+x")
    pc.set_shortcut(Action.RIGHT_HALF, "ctrl+alt+x")
    dupes = pc.shortcut_conflicts()
    assert dupes
    winners = list(dupes.keys())
    losers = [a for vs in dupes.values() for a in vs]
    assert set(winners + losers) == {Action.LEFT_HALF, Action.RIGHT_HALF}


def test_validate_flags_reserved_combo_as_warning_not_error():
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "win+left")
    report = pc.validate()
    assert report.ok            # warnings don't block commit
    assert any("OS-reserved" in w for w in report.warnings)


def test_validate_flags_duplicate_as_warning():
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+alt+x")
    pc.set_shortcut(Action.RIGHT_HALF, "ctrl+alt+x")
    report = pc.validate()
    assert report.ok
    assert any("only one will fire" in w for w in report.warnings)


def test_validate_blocks_on_out_of_range_gap():
    pc = PrefsController(baseline=Settings())
    pc.staged.gap = -1  # bypass clamping via direct attr access
    report = pc.validate()
    assert not report.ok
    assert any("gap" in e for e in report.errors)


def test_commit_calls_callbacks_and_promotes_staged():
    saved: list[Settings] = []
    applied: list[Settings] = []
    pc = PrefsController(baseline=Settings(gap=0))
    pc.set_gap(15)
    report = pc.commit(on_save=saved.append, on_apply=applied.append)
    assert report.ok
    assert saved[0].gap == 15
    assert applied[0].gap == 15
    # Baseline is now the new committed state.
    assert pc.baseline.gap == 15
    assert not pc.is_dirty


def test_commit_blocked_by_errors_does_not_fire_callbacks():
    pc = PrefsController(baseline=Settings())
    pc.staged.gap = -10  # bypass clamp → invalid
    saved: list[Settings] = []
    applied: list[Settings] = []
    report = pc.commit(on_save=saved.append, on_apply=applied.append)
    assert not report.ok
    assert saved == []
    assert applied == []
    # Baseline must not have been mutated.
    assert pc.baseline.gap == 0


def test_revert_restores_baseline():
    pc = PrefsController(baseline=Settings(gap=5))
    pc.set_gap(20)
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+shift+left")
    assert pc.is_dirty
    pc.revert()
    assert not pc.is_dirty
    assert pc.staged.gap == 5


def test_staged_shortcuts_independent_from_baseline():
    """Editing staged.shortcuts must not bleed back into baseline."""
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+alt+x")
    assert pc.baseline.shortcuts[Action.LEFT_HALF] != "ctrl+alt+x"


def test_validation_report_ok_property():
    assert ValidationReport().ok
    assert not ValidationReport(errors=("x",)).ok
    assert ValidationReport(warnings=("y",)).ok
