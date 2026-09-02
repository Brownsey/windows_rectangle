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


def test_validate_blocks_on_out_of_range_almost_maximize_scale():
    pc = PrefsController(baseline=Settings())
    pc.staged.almost_maximize_scale = 5.0  # bypass clamp
    report = pc.validate()
    assert not report.ok
    assert any("almost_maximize_scale" in e for e in report.errors)


def test_validate_blocks_on_out_of_range_cycle_idle_timeout():
    pc = PrefsController(baseline=Settings())
    pc.staged.cycle_idle_timeout = -1.0
    report = pc.validate()
    assert not report.ok
    assert any("cycle_idle_timeout" in e for e in report.errors)


def test_validate_flags_unparseable_combo_as_error():
    pc = PrefsController(baseline=Settings())
    # Bypass set_shortcut (which would raise) to plant a combo with
    # only modifiers (parse rejects "no non-modifier key").
    pc.staged.shortcuts[Action.LEFT_HALF] = "ctrl+alt"
    report = pc.validate()
    assert not report.ok
    assert any("cannot parse" in e for e in report.errors)


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


def test_baseline_independent_from_constructor_arg():
    """The Settings instance passed at construction must not alias
    pc.baseline — otherwise an external mutation (e.g. ctx.apply_settings
    firing while prefs is open) would silently shift is_dirty."""
    live = Settings(gap=10)
    pc = PrefsController(baseline=live)
    assert pc.staged.gap == 10
    assert not pc.is_dirty
    # External mutation: someone else changes the live Settings.
    live.gap = 99
    # PrefsController's baseline and staged stay anchored at 10.
    assert pc.baseline.gap == 10
    assert pc.staged.gap == 10
    assert not pc.is_dirty


def test_validation_report_ok_property():
    assert ValidationReport().ok
    assert not ValidationReport(errors=("x",)).ok
    assert ValidationReport(warnings=("y",)).ok


# ----- open_prefs_window launcher --------------------------------------

from windows_rectangle.ui.preferences import open_prefs_window  # noqa: E402


class _FakeCtx:
    """Tiny stand-in matching what open_prefs_window touches on AppContext."""

    def __init__(self, settings):
        self.settings = settings
        self.applied: list = []
        self.config_store = None

    def apply_settings(self, settings):
        self.applied.append(settings)


class _FakeStore:
    def __init__(self):
        self.saved: list = []

    def save(self, settings):
        self.saved.append(settings)


def _factory_that(edits, *, accept):
    """Build a dialog factory that mutates the controller via `edits(pc)`
    then returns True/False from exec()."""

    class _Dlg:
        def __init__(self, pc):
            self._pc = pc

        def exec(self):
            edits(self._pc)
            return accept

    return _Dlg


def test_open_prefs_window_commit_on_accept():
    ctx = _FakeCtx(Settings(gap=0))
    ctx.config_store = _FakeStore()
    factory = _factory_that(lambda pc: pc.set_gap(15), accept=True)
    report = open_prefs_window(ctx, dialog_factory=factory)
    assert report is not None and report.ok
    assert ctx.applied[0].gap == 15
    assert ctx.config_store.saved[0].gap == 15


def test_open_prefs_window_cancel_does_not_commit():
    ctx = _FakeCtx(Settings(gap=0))
    ctx.config_store = _FakeStore()
    factory = _factory_that(lambda pc: pc.set_gap(15), accept=False)
    report = open_prefs_window(ctx, dialog_factory=factory)
    assert report is None
    assert ctx.applied == []
    assert ctx.config_store.saved == []


def test_open_prefs_window_no_config_store_skips_save_but_still_applies():
    ctx = _FakeCtx(Settings(gap=0))  # config_store remains None
    factory = _factory_that(lambda pc: pc.set_gap(15), accept=True)
    report = open_prefs_window(ctx, dialog_factory=factory)
    assert report is not None and report.ok
    assert ctx.applied[0].gap == 15  # apply_settings still fires


def test_open_prefs_window_invalid_edits_blocks_commit():
    """User pushed gap out of range via direct attr access — commit
    must refuse, and apply/save must not fire."""
    ctx = _FakeCtx(Settings(gap=10))
    ctx.config_store = _FakeStore()

    def bad_edits(pc):
        pc.staged.gap = -50  # bypass set_gap's clamp

    factory = _factory_that(bad_edits, accept=True)
    report = open_prefs_window(ctx, dialog_factory=factory)
    assert report is not None
    assert not report.ok
    assert ctx.applied == []
    assert ctx.config_store.saved == []


def test_open_prefs_window_end_to_end_almost_maximize_scale(tmp_path):
    """Real AppContext + real PrefsController, fake dialog. User changes
    almost_maximize_scale; assert the next ALMOST_MAXIMIZE dispatch
    honours the new value. Covers the iter 60 wiring all the way through
    open_prefs_window."""
    from tests.conftest import FakeWindowManager, make_monitor
    from windows_rectangle.app import build
    from windows_rectangle.core.actions import Action
    from windows_rectangle.core.geometry import Rect

    m1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)
    wm = FakeWindowManager(monitors=[m1])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    ctx = build(Settings(almost_maximize_scale=0.85), wm)

    # Fake dialog that pulls scale from 0.85 to 0.50 and accepts.
    class _Dlg:
        def __init__(self, pc):
            self._pc = pc

        def exec(self):
            self._pc.set_almost_maximize_scale(0.50)
            return True

    report = open_prefs_window(ctx, dialog_factory=_Dlg)
    assert report is not None and report.ok
    # Dispatcher heard the change.
    assert ctx.dispatcher.almost_maximize_scale == 0.50
    # Real ALMOST_MAXIMIZE dispatch produces a 50%-sized rect.
    ctx.dispatcher.dispatch(Action.ALMOST_MAXIMIZE)
    r = wm.windows[101]
    assert r.width == int(1920 * 0.50)
    assert r.height == int(1040 * 0.50)
