"""The workspace editor must remain import-safe without optional Qt."""

import importlib
import sys


def test_workspaces_dialog_import_is_lazy():
    sys.modules.pop("windows_rectangle.ui.workspaces_dialog", None)
    pyside_was_loaded = "PySide6" in sys.modules
    module = importlib.import_module("windows_rectangle.ui.workspaces_dialog")
    assert callable(module.show)
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules
