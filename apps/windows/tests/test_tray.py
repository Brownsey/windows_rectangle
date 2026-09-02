"""Tests for windows_rectangle.ui.tray.

Loading the module must not require PySide6 — Qt is imported lazily
inside `install(...)`. We don't run install() because that needs a
display + QApplication.
"""

import importlib


def test_tray_module_imports_without_pyside6():
    mod = importlib.import_module("windows_rectangle.ui.tray")
    # Public surface should be present.
    assert hasattr(mod, "TrayController")
    assert hasattr(mod, "install")


def test_tray_controller_defaults():
    from windows_rectangle.ui.tray import TrayController

    class FakeCtx:
        pass

    tc = TrayController(ctx=FakeCtx())
    assert tc.icon is None
    assert tc.menu is None
    assert tc.actions is None
    assert tc.on_open_preferences is None


def test_workspace_result_summary_is_compact():
    from types import SimpleNamespace

    from windows_rectangle.ui.tray import _workspace_result_text

    result = SimpleNamespace(
        placements=(
            SimpleNamespace(status="moved"),
            SimpleNamespace(status="moved"),
            SimpleNamespace(status="not_found"),
            SimpleNamespace(status="blocked"),
        )
    )
    assert _workspace_result_text(result) == "2 moved · 1 not found · 1 blocked"


def _make_fake_report(*, bound_count=0, would_bind_count=0, failed_count=0, total=0):
    """Mini stand-in for BindingReport for tooltip unit tests."""

    class FakeReport:
        pass

    r = FakeReport()
    r.bound_count = bound_count
    r.would_bind_count = would_bind_count
    r.failed_count = failed_count
    r.total = total
    return r


def test_tooltip_for_paused_state():
    """When ctx.paused is True the tooltip must say so — otherwise
    "0/22 bound" looks broken instead of intentional."""
    from windows_rectangle.ui.tray import _tooltip_for

    class FakeSettings:
        gap = 8

    class FakeCtx:
        settings = FakeSettings()
        last_binding_report = _make_fake_report(
            bound_count=0,
            would_bind_count=22,
            failed_count=0,
            total=22,
        )
        paused = True

    s = _tooltip_for(FakeCtx())
    assert "paused" in s
    assert "0/22" in s


def test_tooltip_for_active_state_does_not_say_paused():
    from windows_rectangle.ui.tray import _tooltip_for

    class FakeSettings:
        gap = 4

    class FakeCtx:
        settings = FakeSettings()
        last_binding_report = _make_fake_report(
            bound_count=22,
            would_bind_count=22,
            failed_count=0,
            total=22,
        )
        paused = False

    s = _tooltip_for(FakeCtx())
    assert "paused" not in s
    assert "22/22" in s


def test_tooltip_for_initial_no_report():
    """Before any bind has fired the tooltip just shows the gap."""
    from windows_rectangle.ui.tray import _tooltip_for

    class FakeSettings:
        gap = 0

    class FakeCtx:
        settings = FakeSettings()
        last_binding_report = _make_fake_report(
            bound_count=0,
            would_bind_count=0,
            failed_count=0,
            total=0,
        )
        paused = False

    s = _tooltip_for(FakeCtx())
    assert "shortcuts bound" not in s
    assert "0px gap" in s


def test_tray_does_not_eagerly_import_pyside6():
    """Brief §5 #8 + §6: lazy Qt imports keep non-Windows CI clean.
    Importing the module must not pull PySide6 in at module-load time."""
    import sys

    sys.modules.pop("windows_rectangle.ui.tray", None)
    pyside_was_loaded = "PySide6" in sys.modules
    importlib.import_module("windows_rectangle.ui.tray")
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules, "ui.tray should defer PySide6 import to install()"
