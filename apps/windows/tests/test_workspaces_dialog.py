"""The workspace editor must remain import-safe without optional Qt."""

import importlib
import sys
from types import SimpleNamespace

import pytest


def test_workspaces_dialog_import_is_lazy():
    sys.modules.pop("windows_rectangle.ui.workspaces_dialog", None)
    pyside_was_loaded = "PySide6" in sys.modules
    module = importlib.import_module("windows_rectangle.ui.workspaces_dialog")
    assert callable(module.show)
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules


def test_dialog_autosave_keeps_preferences_changed_while_editor_open(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from windows_rectangle.adapters.json_config import JsonConfigStore
    from windows_rectangle.core.workspaces import Workspace
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(Settings(workspaces=(Workspace("one", "Original", ()),)))
    ctx = SimpleNamespace(settings=store.load(), config_store=store)
    ctx.apply_settings = lambda settings: setattr(ctx, "settings", settings)
    dialog = _build(ctx)
    dialog.editor.rename("one", "Edited")

    newer = store.load()
    newer.gap = 19
    store.save(newer)
    ctx.settings = newer
    assert dialog.autosave()
    assert store.load().gap == 19
    assert store.load().workspaces[0].name == "Edited"
    dialog.window.close()
    _ = app
