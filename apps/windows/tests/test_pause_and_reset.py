"""Tests for AppContext.pause_hotkeys/resume_hotkeys and
PrefsController.reset_shortcuts_to_defaults — the iter-5 user-facing
ergonomics features.

Both paths are pure-Python (no Qt, no Win32) — the fake hotkeys adapter
records register/unregister calls, the prefs controller works on
in-memory Settings.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from windows_rectangle.app import bind_hotkeys_via_bus, build
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings

from windows_rectangle.ui.preferences import PrefsController

from .conftest import FakeWindowManager, make_monitor

M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)


@pytest.fixture
def windows():
    wm = FakeWindowManager(monitors=[M1])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    return wm


class _Hot:
    def __init__(self):
        self.registered: list[tuple[str, Callable[[], None]]] = []
        self.unregister_all_calls = 0

    def register(self, combo, cb):
        self.registered.append((combo, cb))
        return len(self.registered)

    def unregister(self, hid):
        pass

    def unregister_all(self):
        self.unregister_all_calls += 1
        self.registered.clear()


# ----- pause / resume -------------------------------------------------


def test_pause_unregisters_and_flips_flag(windows):
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    assert hot.registered  # sanity
    assert ctx.pause_hotkeys() is True
    assert ctx.paused is True
    assert hot.unregister_all_calls == 1
    assert hot.registered == []


def test_pause_is_idempotent(windows):
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    ctx.pause_hotkeys()
    assert ctx.pause_hotkeys() is False  # already paused
    assert hot.unregister_all_calls == 1  # not called again


def test_resume_re_registers_every_shortcut(windows):
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    initial_count = len(hot.registered)
    ctx.pause_hotkeys()
    assert ctx.resume_hotkeys() is True
    assert ctx.paused is False
    assert len(hot.registered) == initial_count


def test_resume_when_not_paused_is_noop(windows):
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    assert ctx.resume_hotkeys() is False


def test_pause_without_adapter_returns_false(windows):
    ctx = build(Settings(), windows)  # no hotkeys adapter
    assert ctx.pause_hotkeys() is False
    assert ctx.paused is False


def test_pause_resume_notifies_subscribers(windows):
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)

    seen: list[Settings] = []
    ctx.subscribe_settings(seen.append)

    ctx.pause_hotkeys()
    assert len(seen) == 1
    ctx.resume_hotkeys()
    assert len(seen) == 2


def test_pause_marks_report_entries_as_paused(windows):
    """The user-facing 'Binding status' dialog should still know what
    *would* re-register on resume — pause sets `report.paused = True`
    and preserves the original `bound` tuple. The currently-live count
    (bound_count) collapses to 0 because the OS-level combos are gone,
    but `would_bind_count` still reflects the staged set."""
    hot = _Hot()
    ctx = build(Settings(), windows, hotkeys=hot)
    bind_hotkeys_via_bus(ctx, hot.register)
    n_would_before = ctx.last_binding_report.would_bind_count
    ctx.pause_hotkeys()
    rep = ctx.last_binding_report
    assert rep.paused is True
    assert rep.bound_count == 0
    assert rep.would_bind_count == n_would_before
    assert rep.failed_count == 0  # no real failures, just paused


# ----- prefs reset ----------------------------------------------------


def test_reset_shortcuts_restores_default_map():
    pc = PrefsController(baseline=Settings())
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+alt+shift+left")
    # Sanity: the override actually staged.
    assert pc.staged.shortcuts[Action.LEFT_HALF] == "ctrl+alt+shift+left"
    pc.reset_shortcuts_to_defaults()
    assert pc.staged.shortcuts == DEFAULT_SHORTCUTS
    # And the dict is a *copy* — mutating staged must not leak back into
    # DEFAULT_SHORTCUTS.
    pc.staged.shortcuts[Action.LEFT_HALF] = "ctrl+alt+left"
    assert DEFAULT_SHORTCUTS[Action.LEFT_HALF] == "ctrl+alt+left"
    pc.staged.shortcuts[Action.LEFT_HALF] = "ctrl+alt+shift+left"
    assert DEFAULT_SHORTCUTS[Action.LEFT_HALF] == "ctrl+alt+left"


def test_reset_shortcuts_does_not_touch_other_settings():
    """Other Settings fields (gap, drag-to-edge, etc.) shouldn't be
    affected — users typically want to keep those when they reset
    shortcut customisations."""
    pc = PrefsController(baseline=Settings(gap=30, drag_to_edge_enabled=False))
    # Re-stage gap so reset has something to leave alone.
    pc.set_gap(42)
    pc.reset_shortcuts_to_defaults()
    assert pc.staged.gap == 42
    assert pc.staged.drag_to_edge_enabled is False


def test_reset_brings_back_unbound_action():
    """Clearing a shortcut then resetting should bring its default back.
    Users have no other way to recover a default after clearing the cell."""
    pc = PrefsController(baseline=Settings())
    pc.clear_shortcut(Action.CENTER)
    assert Action.CENTER not in pc.staged.shortcuts
    pc.reset_shortcuts_to_defaults()
    assert pc.staged.shortcuts[Action.CENTER] == DEFAULT_SHORTCUTS[Action.CENTER]
