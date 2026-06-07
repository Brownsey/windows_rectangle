"""Tests for windows_rectangle.ui.overlay.

The module must import without PySide6 installed (lazy import inside
`install()`). We don't exercise the widget itself in tests.
"""

import importlib


def test_overlay_module_imports_without_pyside6():
    mod = importlib.import_module("windows_rectangle.ui.overlay")
    assert hasattr(mod, "OverlayController")
    assert hasattr(mod, "install")
    assert hasattr(mod, "show_for")
    assert hasattr(mod, "hide")


def test_overlay_controller_defaults():
    from windows_rectangle.ui.overlay import OverlayController
    oc = OverlayController()
    assert oc.widget is None


def test_hide_with_no_widget_is_noop():
    from windows_rectangle.ui.overlay import OverlayController, hide
    hide(OverlayController())  # must not raise
