"""The workspace editor must remain import-safe without optional Qt."""

import importlib
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_workspaces_dialog_import_is_lazy():
    sys.modules.pop("windows_rectangle.ui.workspaces_dialog", None)
    pyside_was_loaded = "PySide6" in sys.modules
    module = importlib.import_module("windows_rectangle.ui.workspaces_dialog")
    assert callable(module.show)
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules


def test_workspace_dialog_builds_with_real_qt():
    from PySide6 import QtWidgets
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctx = SimpleNamespace(
        settings=Settings(),
        config_store=None,
        apply_settings=lambda _settings: None,
    )

    dialog = _build(ctx)

    assert dialog.window.objectName() == "workspaceEditor"
    assert dialog.window.windowTitle() == "Windows Rectangle — Layouts"
    assert dialog.placements.columnCount() == 6
    buttons = {button.text() for button in dialog.window.findChildren(QtWidgets.QPushButton)}
    assert "Add App…" in buttons
    assert "Edit App…" in buttons
    assert "Choose Position…" in buttons
    assert "Launch & Arrange" in buttons
    dialog.window.deleteLater()
    app.processEvents()
