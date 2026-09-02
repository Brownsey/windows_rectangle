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
    from PySide6 import QtCore, QtWidgets
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
    assert dialog.window.windowFlags() & QtCore.Qt.WindowMinimizeButtonHint
    assert dialog.placements.columnCount() == 6
    buttons = {button.text() for button in dialog.window.findChildren(QtWidgets.QPushButton)}
    assert "Add App…" in buttons
    assert "Edit App…" in buttons
    assert "Choose Position…" in buttons
    assert "Launch & Arrange" in buttons
    assert "Save Changes" not in buttons
    assert "Done" in buttons
    assert isinstance(dialog.shortcut_edit, QtWidgets.QPushButton)
    assert dialog.shortcut_edit.accessibleName() == "Launch shortcut"
    by_label = {
        button.text(): button for button in dialog.window.findChildren(QtWidgets.QPushButton)
    }
    for label in ("Use a Template…", "New Layout", "Capture Open Apps…"):
        assert by_label[label].isEnabled()
    for label in (
        "Duplicate Layout",
        "Delete Layout",
        "Add App…",
        "Edit App…",
        "Remove App",
        "Choose Position…",
        "Record current positions",
        "Test matches",
        "Launch & Arrange",
    ):
        assert not by_label[label].isEnabled()
    dialog.window.deleteLater()
    app.processEvents()


def test_workspace_controls_enable_only_when_their_target_exists():
    from PySide6 import QtWidgets
    from windows_rectangle.core.workspaces import (
        NormalizedRect,
        WindowMatcher,
        Workspace,
        WorkspacePlacement,
    )
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    placement = WorkspacePlacement(
        "client",
        "RuneLite",
        WindowMatcher(process_name="RuneLite.exe"),
        NormalizedRect(0, 0, 10000, 10000),
    )
    ctx = SimpleNamespace(
        settings=Settings(workspaces=(Workspace("gaming", "Gaming", (placement,)),)),
        config_store=None,
        apply_settings=lambda _settings: None,
    )
    dialog = _build(ctx)
    by_label = {
        button.text(): button for button in dialog.window.findChildren(QtWidgets.QPushButton)
    }

    for label in (
        "Duplicate Layout",
        "Delete Layout",
        "Add App…",
        "Record current positions",
        "Test matches",
        "Launch & Arrange",
    ):
        assert by_label[label].isEnabled()
    for label in ("Edit App…", "Remove App", "Choose Position…"):
        assert not by_label[label].isEnabled()

    dialog.placements.selectRow(0)
    app.processEvents()

    for label in ("Edit App…", "Remove App", "Choose Position…"):
        assert by_label[label].isEnabled()
    dialog.window.deleteLater()
    app.processEvents()


def test_workspace_shortcut_records_modifier_combo_and_autosaves():
    from PySide6 import QtCore, QtTest, QtWidgets
    from windows_rectangle.core.workspaces import Workspace
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    saved = []
    hotkey_calls = []
    settings = Settings(workspaces=(Workspace("gaming", "Gaming", ()),))
    ctx = SimpleNamespace(
        settings=settings,
        config_store=SimpleNamespace(save=saved.append),
        hotkeys=SimpleNamespace(unregister_all=lambda: hotkey_calls.append("suspend")),
    )

    def apply_settings(updated):
        ctx.settings = updated

    ctx.apply_settings = apply_settings
    ctx.rebind_hotkeys = lambda: hotkey_calls.append("resume")
    dialog = _build(ctx)
    dialog.window.show()
    app.processEvents()

    def record_combo():
        modal = app.activeModalWidget()
        assert modal is not None
        editor = modal.findChild(QtWidgets.QKeySequenceEdit, "recordShortcutEditor")
        assert editor is not None
        QtTest.QTest.keyClick(
            editor,
            QtCore.Qt.Key_1,
            QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier,
        )

    QtCore.QTimer.singleShot(50, record_combo)
    dialog.shortcut_edit.click()
    app.processEvents()

    assert saved[-1].workspaces[0].shortcut == "ctrl+alt+1"
    assert hotkey_calls == ["suspend", "resume"]
    dialog.window.deleteLater()
    app.processEvents()


def test_workspace_binding_failure_is_visible_after_save():
    from PySide6 import QtWidgets
    from windows_rectangle.core.workspaces import Workspace
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    workspace = Workspace("gaming", "Gaming", (), "ctrl+alt+1")
    ctx = SimpleNamespace(
        settings=Settings(workspaces=(workspace,)),
        config_store=None,
        apply_settings=lambda _settings: None,
        last_binding_report=SimpleNamespace(
            workspace_failed=(("gaming", "Gaming", "ctrl+alt+1", "already registered"),)
        ),
    )

    dialog = _build(ctx)

    assert dialog.status.property("status") == "error"
    assert "could not be registered" in dialog.status.text()
    assert "Choose another shortcut" in dialog.status.text()
    dialog.window.deleteLater()
    app.processEvents()


def test_workspace_inline_duplicate_name_is_rejected_and_valid_rename_refreshes_list():
    from PySide6 import QtCore, QtTest, QtWidgets
    from windows_rectangle.core.workspaces import Workspace
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings = Settings(
        workspaces=(
            Workspace("gaming", "Gaming", ()),
            Workspace("office", "Office", ()),
        )
    )
    saved = []
    ctx = SimpleNamespace(
        settings=settings,
        config_store=SimpleNamespace(save=saved.append),
        apply_settings=lambda _settings: None,
    )
    dialog = _build(ctx)
    dialog.window.show()
    app.processEvents()

    dialog.name_edit.setText("office")
    QtTest.QTest.keyClick(dialog.name_edit, QtCore.Qt.Key_Return)
    app.processEvents()

    assert dialog.window.isVisible()
    assert dialog.name_edit.text() == "Gaming"
    assert dialog.status.property("status") == "error"
    assert saved == []

    dialog.name_edit.setText("Games")
    QtTest.QTest.keyClick(dialog.name_edit, QtCore.Qt.Key_Return)
    app.processEvents()

    assert dialog.window.isVisible()
    assert dialog.workspace_list.currentItem().text() == "Games"
    assert saved[-1].workspaces[0].name == "Games"
    assert len(saved) == 1
    dialog.window.deleteLater()
    app.processEvents()


def test_workspace_escape_and_close_use_dirty_change_guard(monkeypatch):
    from PySide6 import QtCore, QtTest, QtWidgets
    from windows_rectangle.core.workspaces import Workspace
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctx = SimpleNamespace(
        settings=Settings(workspaces=(Workspace("gaming", "Gaming", ()),)),
        config_store=None,
        apply_settings=lambda _settings: None,
    )
    dialog = _build(ctx)
    dialog.window.show()
    dialog.editor.rename("gaming", "Unsaved")
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *_args: QtWidgets.QMessageBox.Cancel,
    )

    QtTest.QTest.keyClick(dialog.window, QtCore.Qt.Key_Escape)
    app.processEvents()

    assert dialog.window.isVisible()
    assert dialog.editor.is_dirty

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *_args: QtWidgets.QMessageBox.Discard,
    )
    dialog.window.close()
    app.processEvents()

    assert not dialog.window.isVisible()
    assert not dialog.editor.is_dirty
    dialog.window.deleteLater()
    app.processEvents()


def test_editing_match_rule_clears_stale_test_result(monkeypatch):
    from PySide6 import QtWidgets
    from windows_rectangle.core.workspaces import (
        NormalizedRect,
        WindowMatcher,
        Workspace,
        WorkspacePlacement,
    )
    from windows_rectangle.ports.config_store import Settings

    from windows_rectangle.ui import workspaces_dialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    placement = WorkspacePlacement(
        "client",
        "Browser",
        WindowMatcher(process_name="chrome.exe", title_contains="Docs"),
        NormalizedRect(0, 0, 10000, 10000),
    )
    ctx = SimpleNamespace(
        settings=Settings(workspaces=(Workspace("web", "Web", (placement,)),)),
        config_store=None,
        apply_settings=lambda _settings: None,
    )
    dialog = workspaces_dialog._build(ctx)
    dialog.match_results[placement.id] = True
    dialog.load_selected()
    dialog.placements.selectRow(0)
    monkeypatch.setattr(
        workspaces_dialog,
        "_application_rule_dialog",
        lambda *_args: {
            "name": "Browser",
            "process_name": "chrome.exe",
            "title_contains": "Mail",
            "title_regex": "",
            "launch_command": "",
            "monitor_index": 0,
            "preset_id": "full",
        },
    )

    workspaces_dialog._edit_application(dialog, QtWidgets)

    assert placement.id not in dialog.match_results
    assert dialog.placements.item(0, 5).text() == "Not tested"
    dialog.window.deleteLater()
    app.processEvents()


def test_add_app_dialog_keeps_invalid_input_open_with_inline_error():
    from PySide6 import QtCore, QtWidgets
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _application_rule_dialog, _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctx = SimpleNamespace(
        settings=Settings(),
        config_store=None,
        apply_settings=lambda _settings: None,
        windows=SimpleNamespace(list_work_areas=lambda: [object(), object()]),
    )
    controller = _build(ctx)
    observed = {}

    def submit_invalid_form():
        modal = app.activeModalWidget()
        assert modal is not None
        buttons = modal.findChild(QtWidgets.QDialogButtonBox)
        assert buttons is not None
        buttons.button(QtWidgets.QDialogButtonBox.Save).click()
        app.processEvents()
        error = modal.findChild(QtWidgets.QLabel, "appRuleError")
        display = modal.findChild(QtWidgets.QSpinBox)
        observed["visible"] = modal.isVisible()
        observed["error"] = error.text() if error is not None else ""
        observed["display_maximum"] = display.maximum() if display is not None else 0
        if modal.isVisible():
            buttons.button(QtWidgets.QDialogButtonBox.Cancel).click()

    QtCore.QTimer.singleShot(50, submit_invalid_form)
    result = _application_rule_dialog(controller, QtWidgets)

    assert result is None
    assert observed == {
        "visible": True,
        "error": "Enter an app or account name",
        "display_maximum": 2,
    }
    controller.window.deleteLater()
    app.processEvents()


def test_edit_app_preserves_saved_disconnected_display_number():
    from PySide6 import QtCore, QtWidgets
    from windows_rectangle.core.workspaces import (
        NormalizedRect,
        WindowMatcher,
        WorkspacePlacement,
    )
    from windows_rectangle.ports.config_store import Settings
    from windows_rectangle.ui.workspaces_dialog import _application_rule_dialog, _build

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ctx = SimpleNamespace(
        settings=Settings(),
        config_store=None,
        apply_settings=lambda _settings: None,
        windows=SimpleNamespace(list_work_areas=lambda: [object()]),
    )
    controller = _build(ctx)
    placement = WorkspacePlacement(
        "browser",
        "Browser",
        WindowMatcher(process_name="chrome.exe"),
        NormalizedRect(0, 0, 10000, 10000),
        monitor_index=1,
    )
    observed = {}

    def inspect_and_cancel():
        modal = app.activeModalWidget()
        assert modal is not None
        display = modal.findChild(QtWidgets.QSpinBox)
        assert display is not None
        observed["value"] = display.value()
        observed["maximum"] = display.maximum()
        modal.reject()

    QtCore.QTimer.singleShot(50, inspect_and_cancel)
    result = _application_rule_dialog(controller, QtWidgets, placement)

    assert result is None
    assert observed == {"value": 2, "maximum": 2}
    controller.window.deleteLater()
    app.processEvents()
