"""Tests for BindingReport bookkeeping + the binding-status formatter.

Two layers:
  * `windows_rectangle.app.BindingReport` is populated by
    `_bind_shortcuts` as a side effect on AppContext. Verify the report
    captures successes and per-action failure messages.
  * `windows_rectangle.ui.binding_status_view` renders that report into
    text/HTML for the tray's "Binding status…" popup.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from windows_rectangle.app import (
    EMPTY_BINDING_REPORT,
    BindingReport,
    bind_hotkeys,
    bind_hotkeys_via_bus,
    build,
)
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui.binding_status_view import (
    binding_status_html,
    binding_status_text,
)

from .conftest import FakeWindowManager, make_monitor

M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)


@pytest.fixture
def windows():
    wm = FakeWindowManager(monitors=[M1])
    wm.windows[101] = Rect(100, 100, 800, 600)
    wm.active = 101
    return wm


def test_empty_report_defaults(windows):
    ctx = build(Settings(), windows)
    assert ctx.last_binding_report is EMPTY_BINDING_REPORT
    assert ctx.last_binding_report.total == 0
    assert ctx.last_binding_report.all_bound is False


class _AlwaysOK:
    def __init__(self) -> None:
        self.registered: list[tuple[str, Callable[[], None]]] = []

    def register(self, combo, cb):
        self.registered.append((combo, cb))
        return len(self.registered)


def test_bind_hotkeys_populates_report_on_success(windows):
    ctx = build(Settings(), windows)
    hot = _AlwaysOK()
    n = bind_hotkeys(ctx, hot.register)
    assert n == len(DEFAULT_SHORTCUTS)
    report = ctx.last_binding_report
    assert report.bound_count == len(DEFAULT_SHORTCUTS)
    assert report.failed_count == 0
    assert report.all_bound is True
    # Every action should appear in `bound`.
    actions = {a for a, _ in report.bound}
    assert actions == set(DEFAULT_SHORTCUTS.keys())


def test_bind_hotkeys_records_failures_with_message(windows):
    """If register raises for an action, the BindingReport must capture
    the action, the combo, and the str() of the exception. That's what
    the tray dialog renders for the user — losing it strands the UI."""

    def register(combo, cb):
        if combo == DEFAULT_SHORTCUTS[Action.LEFT_HALF]:
            raise RuntimeError("combo already in use")
        return 1

    ctx = build(Settings(), windows)
    bound = bind_hotkeys(ctx, register)
    assert bound == len(DEFAULT_SHORTCUTS) - 1
    report = ctx.last_binding_report
    assert report.failed_count == 1
    action, combo, msg = report.failed[0]
    assert action is Action.LEFT_HALF
    assert combo == DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    assert "combo already in use" in msg
    assert report.all_bound is False


def test_bind_hotkeys_via_bus_also_populates_report(windows):
    ctx = build(Settings(), windows)
    hot = _AlwaysOK()
    bind_hotkeys_via_bus(ctx, hot.register)
    assert ctx.last_binding_report.bound_count == len(DEFAULT_SHORTCUTS)


def test_rebind_repopulates_report(windows):
    """Re-binding must overwrite, not append to, the previous report —
    otherwise a successful rebind would still show stale failures."""

    failing_combo = DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    call_count = {"n": 0}

    def register(combo, cb):
        call_count["n"] += 1
        # First pass: LEFT_HALF fails. Second pass: nothing fails.
        if combo == failing_combo and call_count["n"] <= len(DEFAULT_SHORTCUTS):
            raise RuntimeError("first pass clash")
        return call_count["n"]

    ctx = build(Settings(), windows)
    bind_hotkeys(ctx, register)
    assert ctx.last_binding_report.failed_count == 1

    bind_hotkeys(ctx, register)
    # Second pass: call_count is past len(DEFAULT_SHORTCUTS), no failures.
    assert ctx.last_binding_report.failed_count == 0
    assert ctx.last_binding_report.bound_count == len(DEFAULT_SHORTCUTS)


# ----- formatter tests -----------------------------------------------


def test_text_none_or_empty_report():
    assert binding_status_text(None) == "No hotkey binding has run yet."
    assert binding_status_text(EMPTY_BINDING_REPORT) == "No hotkey binding has run yet."


def test_text_includes_bound_and_failed_sections():
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=((Action.RIGHT_HALF, "ctrl+alt+right", "combo already in use"),),
    )
    text = binding_status_text(report)
    assert "1 of 2 shortcuts bound." in text
    assert "Bound:" in text
    assert "ctrl+alt+left" in text
    assert "Failed:" in text
    assert "ctrl+alt+right" in text
    assert "combo already in use" in text


def test_html_escapes_user_strings_in_failures():
    """Defensive: if a Win32 exception message ever contained <html>, the
    UI must escape it rather than letting Qt render markup."""
    report = BindingReport(
        bound=(),
        failed=((Action.RIGHT_HALF, "ctrl+alt+right", "<b>oops</b>"),),
    )
    out = binding_status_html(report)
    assert "<b>oops</b>" not in out
    assert "&lt;b&gt;oops&lt;/b&gt;" in out


def test_html_none_or_empty_report():
    out = binding_status_html(None)
    assert "No hotkey binding has run yet" in out
    assert binding_status_html(EMPTY_BINDING_REPORT) == out


def test_html_summary_mentions_failed_count_when_any_failed():
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=((Action.RIGHT_HALF, "ctrl+alt+right", "boom"),),
    )
    out = binding_status_html(report)
    # The "X of Y" line may include <b> tags around the numerals — assert
    # on the substrings that have to be present rather than the formatted
    # string itself.
    assert ">1</b>" in out and ">2</b>" in out
    assert "1 failed" in out


def test_html_clean_when_everything_bound():
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=(),
    )
    out = binding_status_html(report)
    assert ">1</b>" in out
    # No failed-count, no "Failed" header.
    assert "failed" not in out.lower()


# ----- paused state rendering -----------------------------------------


def test_paused_report_html_uses_resume_header():
    """A paused report shouldn't render entries as 'Bound' — they're not
    currently live. The 'Would re-register on resume' header makes the
    state clear, and the summary line marks "(paused)"."""
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=(),
        paused=True,
    )
    out = binding_status_html(report)
    assert "(paused)" in out
    assert "Would re-register on resume" in out
    assert "Bound</h4>" not in out


def test_paused_text_renders_distinctly():
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=(),
        paused=True,
    )
    out = binding_status_text(report)
    assert "(paused)" in out
    assert "Would re-register on resume:" in out


def test_paused_empty_report_html_message():
    """No prior binding ever ran but the user paused (corner case) —
    still get a paused-aware message rather than 'no binding has run'."""
    report = BindingReport(bound=(), failed=(), paused=True)
    out = binding_status_html(report)
    assert "paused" in out.lower()


def test_bound_count_collapses_when_paused():
    """The currently-live count must be 0 while paused (nothing is
    registered with Windows), but would_bind_count keeps the staged
    number visible for the tooltip / dialog."""
    report = BindingReport(
        bound=((Action.LEFT_HALF, "ctrl+alt+left"),),
        failed=(),
        paused=True,
    )
    assert report.bound_count == 0
    assert report.would_bind_count == 1
    assert report.all_bound is False
