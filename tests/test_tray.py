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


def test_tray_does_not_eagerly_import_pyside6():
    """Brief §5 #8 + §6: lazy Qt imports keep non-Windows CI clean.
    Importing the module must not pull PySide6 in at module-load time."""
    import sys

    sys.modules.pop("windows_rectangle.ui.tray", None)
    pyside_was_loaded = "PySide6" in sys.modules
    importlib.import_module("windows_rectangle.ui.tray")
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules, (
            "ui.tray should defer PySide6 import to install()"
        )
