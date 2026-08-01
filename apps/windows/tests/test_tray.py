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
