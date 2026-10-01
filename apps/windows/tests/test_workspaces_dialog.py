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


def test_workspace_controls_visible_at_960_by_520_without_scrolling(
    workspace_qt, tmp_path, monkeypatch
):
    qt_widgets, app = workspace_qt
    from PySide6 import QtCore

    from windows_rectangle.ui.workspaces_dialog import _build

    app.setStyle("windowsvista")
    monkeypatch.setattr(
        qt_widgets.QApplication,
        "primaryScreen",
        lambda: SimpleNamespace(availableGeometry=lambda: QtCore.QRect(0, 0, 960, 520)),
    )
    context, _store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()

    assert dialog.window.width() <= 960
    assert dialog.window.height() <= 520
    assert dialog.window.findChild(qt_widgets.QScrollArea, "workspaceContentScroll") is None
    buttons = {
        button.text(): button for button in dialog.window.findChildren(qt_widgets.QPushButton)
    }
    for label in (
        "New empty workspace",
        "Add application…",
        "Remove selected rule",
        "Record current positions",
        "Test matches",
        "Restore now",
        "Save now",
        "Done",
    ):
        button = buttons[label]
        top_left = button.mapTo(dialog.window, QtCore.QPoint(0, 0))
        assert button.isVisible()
        assert top_left.x() >= 0 and top_left.x() + button.width() <= dialog.window.width()
        assert top_left.y() >= 0 and top_left.y() + button.height() <= dialog.window.height()
    assert dialog.canvas.height() >= 120
    assert dialog.placements.height() >= 60


def test_workspace_controls_reachable_on_512_by_360_screen(workspace_qt, tmp_path, monkeypatch):
    qt_widgets, app = workspace_qt
    from PySide6 import QtCore

    from windows_rectangle.ui.workspaces_dialog import _build

    app.setStyle("windowsvista")
    monkeypatch.setattr(
        qt_widgets.QApplication,
        "primaryScreen",
        lambda: SimpleNamespace(availableGeometry=lambda: QtCore.QRect(0, 0, 512, 360)),
    )
    context, _store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()

    assert dialog.window.width() <= 512
    assert dialog.window.height() <= 360
    scroll = dialog.window.findChild(qt_widgets.QScrollArea, "workspaceContentScroll")
    assert scroll is not None
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() > 0
    buttons = {
        button.text(): button for button in dialog.window.findChildren(qt_widgets.QPushButton)
    }
    for label in (
        "Start from template…",
        "New empty workspace",
        "Capture current windows…",
        "Duplicate workspace",
        "Delete workspace",
        "Add application…",
        "Remove selected rule",
        "Record current positions",
        "Test matches",
        "Restore now",
        "Done",
    ):
        button = buttons[label]
        for area in reversed(dialog.window.findChildren(qt_widgets.QScrollArea)):
            area.ensureWidgetVisible(button)
        app.processEvents()
        top_left = button.mapTo(dialog.window, QtCore.QPoint(0, 0))
        assert button.isVisible(), label
        assert 0 <= top_left.x() <= dialog.window.width() - button.width(), label
        assert 0 <= top_left.y() <= dialog.window.height() - button.height(), label


def test_compact_workspace_save_failure_status_fits_screen(workspace_qt, tmp_path, monkeypatch):
    qt_widgets, app = workspace_qt
    from PySide6 import QtCore

    from windows_rectangle.ui.workspaces_dialog import _build

    monkeypatch.setattr(
        qt_widgets.QApplication,
        "primaryScreen",
        lambda: SimpleNamespace(availableGeometry=lambda: QtCore.QRect(0, 0, 512, 360)),
    )
    context, store = _workspace_context(tmp_path)
    dialog = _build(context)
    dialog.window.show()
    app.processEvents()

    def fail_save(_settings):
        raise OSError(
            "Access to the configuration file was denied by another program. "
            "Close the editor using the file and retry saving your changes."
        )

    store.save = fail_save
    dialog.name_edit.setText("Project revised")
    dialog.name_edit.editingFinished.emit()
    app.processEvents()

    assert dialog.editor.is_dirty
    assert dialog.status.text().startswith("Autosave failed:")
    assert dialog.window.width() <= 512
    assert dialog.window.height() <= 360
    assert dialog.status.wordWrap()
    assert dialog.status.height() >= dialog.status.fontMetrics().lineSpacing() * 2
    assert dialog.status.width() <= dialog.window.width()
    assert dialog.apply_button.isVisible()
    scroll = dialog.window.findChild(qt_widgets.QScrollArea, "workspaceContentScroll")
    restore = next(
        button
        for button in dialog.window.findChildren(qt_widgets.QPushButton)
        if button.text() == "Restore now"
    )
    scroll.ensureWidgetVisible(restore)
    app.processEvents()
    restore_top = restore.mapTo(dialog.window, QtCore.QPoint(0, 0))
    assert restore_top.y() >= 0
    assert restore_top.y() + restore.height() <= dialog.window.height()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native layout")
def test_native_workspace_actions_fit_or_scroll_at_200_percent():
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

        def fully_visible(button):
            rect = QtCore.QRect(button.mapTo(dialog.window, QtCore.QPoint(0, 0)), button.size())
            if not dialog.window.rect().contains(rect):
                return False
            for area in dialog.window.findChildren(QtWidgets.QScrollArea):
                if area.isAncestorOf(button):
                    in_viewport = QtCore.QRect(
                        button.mapTo(area.viewport(), QtCore.QPoint(0, 0)), button.size()
                    )
                    if not area.viewport().rect().contains(in_viewport):
                        return False
            return button.isVisible()

        footer_initial = all(fully_visible(buttons[label]) for label in ("Done", "Save now"))
        toolbar = (
            "Add application…", "Remove selected rule", "Record current positions",
            "Test matches", "Restore now",
        )
        compact_actions = (
            "Start from template…", "New empty workspace", "Capture current windows…",
            "Duplicate workspace", "Delete workspace", *toolbar,
        )
        compact_scroll = dialog.window.findChild(QtWidgets.QScrollArea, "workspaceContentScroll")
        wide = screen.width() >= 960
        if wide:
            actions_visible = {
                label: fully_visible(buttons[label]) for label in toolbar
            }
        else:
            actions_visible = {}
            if compact_scroll is not None:
                for label in compact_actions:
                    compact_scroll.ensureWidgetVisible(buttons[label], 0, 0)
                    app.processEvents()
                    actions_visible[label] = fully_visible(buttons[label])
        print(json.dumps({
            "width": dialog.window.width(), "height": dialog.window.height(),
            "available": [screen.width(), screen.height()],
            "frame_fits": screen.contains(frame),
            "footer_initial": footer_initial,
            "wide": wide,
            "compact_scroll": compact_scroll is not None,
            "horizontal_overflow": compact_scroll.horizontalScrollBar().maximum() if compact_scroll else None,
            "actions_visible": actions_visible,
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
    assert layout["footer_initial"]
    assert layout["actions_visible"] and all(layout["actions_visible"].values())
    if layout["wide"]:
        assert not layout["compact_scroll"]
    else:
        assert layout["compact_scroll"]
        assert layout["horizontal_overflow"] == 0
