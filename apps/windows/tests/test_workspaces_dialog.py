"""The workspace editor must remain import-safe without optional Qt."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest


@pytest.fixture
def workspace_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    qt_widgets = pytest.importorskip("PySide6.QtWidgets")
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    yield qt_widgets, app
    for widget in app.topLevelWidgets():
        widget.hide()
        widget.deleteLater()
    app.processEvents()


def _workspace_context(tmp_path, *, windows=1, placements=1):
    from windows_rectangle.adapters.json_config import JsonConfigStore
    from windows_rectangle.app import build
    from windows_rectangle.core.geometry import Rect
    from windows_rectangle.core.workspaces import (
        NormalizedRect,
        WindowIdentity,
        WindowMatcher,
        Workspace,
        WorkspacePlacement,
    )
    from windows_rectangle.ports.config_store import Settings

    class WorkspaceWindows:
        blocked = False

        def __init__(self):
            self.open = [
                WindowIdentity(index, f"Plan {index}", "chrome.exe") for index in range(windows)
            ]
            self.rects = {index: Rect(100, 100, 500, 400) for index in range(windows)}

        def list_windows(self):
            return list(self.open)

        def list_work_areas(self):
            return [Rect(0, 0, 1920, 1080)]

        def get_window_rect(self, handle):
            return self.rects[handle]

        def monitor_index_for_window(self, handle):
            return 0

        def is_maximized(self, handle):
            return False

        def restore_window(self, handle):
            pass

        def set_window_rect(self, handle, rect):
            if self.blocked:
                return False
            self.rects[handle] = rect
            return True

    rules = tuple(
        WorkspacePlacement(
            f"rule-{index}",
            f"Plan {index}",
            WindowMatcher("chrome.exe", f"Plan {index}"),
            NormalizedRect(0, 0, 10000, 10000),
        )
        for index in range(placements)
    )
    settings = Settings(workspaces=(Workspace("one", "Project", rules),), active_workspace_id="one")
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(settings)
    context = build(store.load(), WorkspaceWindows(), config_store=store)
    return context, store


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


def test_rule_edit_invalidates_previous_match_result(workspace_qt, tmp_path):
    qt_widgets, app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build, _test_matches

    context, store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()
    _test_matches(dialog, qt_widgets)
    assert dialog.placements.item(0, 6).text() == "Matched"

    dialog.placements.item(0, 1).setText("missing.exe")
    app.processEvents()

    assert dialog.placements.item(0, 6).text() == "Not tested"
    assert store.load().workspaces[0].placements[0].matcher.process_name == "missing.exe"


@pytest.mark.parametrize(("column", "value"), [(4, "invalid"), (3, "[")])
def test_invalid_rule_edit_does_not_retain_stale_match(workspace_qt, tmp_path, column, value):
    qt_widgets, app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build, _test_matches

    context, _store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()
    _test_matches(dialog, qt_widgets)
    assert dialog.placements.item(0, 6).text() == "Matched"

    dialog.placements.item(0, column).setText(value)
    app.processEvents()

    assert dialog.placements.item(0, 6).text() != "Matched"
    assert "invalid" in dialog.status.text()


@pytest.mark.parametrize(
    ("open_windows", "rules", "blocked", "expected", "title_fragment"),
    [
        (0, 1, False, "not found", "not restored"),
        (1, 1, True, "blocked", "not restored"),
        (1, 2, False, "not found", "partly"),
    ],
)
def test_incomplete_restore_warns_instead_of_claiming_restored(
    workspace_qt, tmp_path, monkeypatch, open_windows, rules, blocked, expected, title_fragment
):
    qt_widgets, _app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build, _restore

    context, _store = _workspace_context(tmp_path, windows=open_windows, placements=rules)
    context.windows.blocked = blocked
    dialog = _build(context)
    notices = []
    monkeypatch.setattr(
        qt_widgets.QMessageBox,
        "warning",
        lambda _parent, title, message: notices.append(("warning", title, message)),
    )
    monkeypatch.setattr(
        qt_widgets.QMessageBox,
        "information",
        lambda _parent, title, message: notices.append(("information", title, message)),
    )

    _restore(dialog, qt_widgets)

    assert len(notices) == 1
    assert notices[0][0] == "warning"
    assert title_fragment in notices[0][1].lower()
    assert expected in notices[0][2]


def test_empty_workspace_restore_explains_nothing_happened(workspace_qt, tmp_path, monkeypatch):
    qt_widgets, _app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build, _restore

    context, _store = _workspace_context(tmp_path, placements=0)
    dialog = _build(context)
    notices = []
    monkeypatch.setattr(
        qt_widgets.QMessageBox,
        "warning",
        lambda _parent, title, message: notices.append(("warning", title, message)),
    )
    monkeypatch.setattr(
        qt_widgets.QMessageBox,
        "information",
        lambda _parent, title, message: notices.append(("information", title, message)),
    )

    _restore(dialog, qt_widgets)

    assert len(notices) == 1
    assert notices[0][0] == "warning"
    assert "no windows" in notices[0][2].lower()


def test_successful_restore_still_uses_information(workspace_qt, tmp_path, monkeypatch):
    qt_widgets, _app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build, _restore

    context, _store = _workspace_context(tmp_path)
    dialog = _build(context)
    notices = []
    monkeypatch.setattr(
        qt_widgets.QMessageBox,
        "information",
        lambda _parent, title, message: notices.append((title, message)),
    )

    _restore(dialog, qt_widgets)

    assert len(notices) == 1
    assert "1 moved" in notices[0][1]


def test_save_retry_updates_workspace_list_without_reopen(workspace_qt, tmp_path):
    qt_widgets, app = workspace_qt
    from windows_rectangle.ui.workspaces_dialog import _build

    context, store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()
    original_save = store.save

    def fail_save(_settings):
        raise OSError("disk unavailable")

    store.save = fail_save
    dialog.name_edit.setText("Project revised")
    dialog.name_edit.editingFinished.emit()
    assert dialog.editor.is_dirty
    assert store.load().workspaces[0].name == "Project"

    store.save = original_save
    dialog.apply_button.click()
    app.processEvents()

    assert store.load().workspaces[0].name == "Project revised"
    assert dialog.workspace_list.currentItem().text() == "Project revised"
    assert dialog.selected_id == "one"
    assert not dialog.editor.is_dirty


def test_workspace_controls_reachable_at_960_by_520(workspace_qt, tmp_path):
    qt_widgets, app = workspace_qt
    from PySide6 import QtCore

    from windows_rectangle.ui.workspaces_dialog import _build

    app.setStyle("windowsvista")
    context, _store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.resize(960, 520)
    dialog.window.show()
    app.processEvents()

    assert dialog.window.width() <= 960
    assert dialog.window.height() <= 520
    buttons = {
        button.text(): button for button in dialog.window.findChildren(qt_widgets.QPushButton)
    }
    for label in ("New empty workspace", "Add application…", "Test matches", "Restore now", "Done"):
        button = buttons[label]
        for area in dialog.window.findChildren(qt_widgets.QScrollArea):
            area.ensureWidgetVisible(button)
        app.processEvents()
        top_left = button.mapTo(dialog.window, QtCore.QPoint(0, 0))
        assert button.isVisible()
        assert top_left.x() >= 0 and top_left.x() + button.width() <= dialog.window.width()
        assert top_left.y() >= 0 and top_left.y() + button.height() <= dialog.window.height()
    assert dialog.canvas.height() >= 120
    assert dialog.placements.height() >= 60


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native layout")
def test_native_workspace_actions_fit_at_200_percent_without_scrolling():
    script = dedent("""
        import json
        from PySide6 import QtCore, QtWidgets
        from windows_rectangle.app import build
        from windows_rectangle.ports.config_store import Settings
        from windows_rectangle.ui.workspaces_dialog import _build
        class EmptyWindows:
            def list_windows(self): return []
            def list_work_areas(self): return []
        app = QtWidgets.QApplication([])
        dialog = _build(build(Settings(), EmptyWindows()))
        dialog.window.show()
        app.processEvents()
        buttons = {button.text(): button for button in dialog.window.findChildren(QtWidgets.QPushButton)}
        screen = dialog.window.screen().availableGeometry()
        frame = dialog.window.frameGeometry()
        print(json.dumps({
            "width": dialog.window.width(), "height": dialog.window.height(),
            "available": [screen.width(), screen.height()],
            "frame_fits": screen.contains(frame),
            "done_bottom": buttons["Done"].mapTo(dialog.window, QtCore.QPoint(0, buttons["Done"].height())).y(),
            "add_bottom": buttons["Add application…"].mapTo(dialog.window, QtCore.QPoint(0, buttons["Add application…"].height())).y(),
            "test_bottom": buttons["Test matches"].mapTo(dialog.window, QtCore.QPoint(0, buttons["Test matches"].height())).y(),
            "restore_bottom": buttons["Restore now"].mapTo(dialog.window, QtCore.QPoint(0, buttons["Restore now"].height())).y(),
        }))
        dialog.window.hide()
    """)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "windows"
    env["QT_SCALE_FACTOR"] = "2"
    env["PYTHONPATH"] = (
        str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=20
    )
    assert result.returncode == 0, result.stderr
    layout = json.loads(result.stdout)
    assert layout["frame_fits"]
    assert layout["height"] <= layout["available"][1]
    assert layout["done_bottom"] <= layout["height"]
    assert layout["add_bottom"] <= layout["height"]
    assert layout["test_bottom"] <= layout["height"]
    assert layout["restore_bottom"] <= layout["height"]
