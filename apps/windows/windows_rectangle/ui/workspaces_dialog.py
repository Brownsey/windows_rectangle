"""Accessible PySide6 editor for captured multi-window workspaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from ..core.workspace_service import WorkspaceWindows, apply_workspace
from .workspace_editor import WorkspaceEditorController

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkspaceDialog:
    ctx: object
    editor: WorkspaceEditorController
    window: object
    workspace_list: object
    name_edit: object
    shortcut_edit: object
    placements: object
    status: object
    apply_button: object
    selected_id: str = ""
    loading: bool = False

    def refresh(self) -> None:
        from PySide6 import QtCore, QtWidgets

        self.loading = True
        try:
            self.workspace_list.clear()
            selected_row = 0
            for row, workspace in enumerate(self.editor.staged.workspaces):
                item = QtWidgets.QListWidgetItem(workspace.name)
                item.setData(QtCore.Qt.UserRole, workspace.id)
                item.setToolTip(
                    f"{len(workspace.placements)} windows"
                    + (f" · {workspace.shortcut}" if workspace.shortcut else "")
                )
                self.workspace_list.addItem(item)
                if workspace.id == self.selected_id:
                    selected_row = row
            if self.editor.staged.workspaces:
                self.workspace_list.setCurrentRow(selected_row)
            else:
                self.selected_id = ""
                self.name_edit.clear()
                self.shortcut_edit.clear()
                self.placements.setRowCount(0)
        finally:
            self.loading = False
        self.update_validation()

    def load_selected(self) -> None:
        from PySide6 import QtCore, QtWidgets

        item = self.workspace_list.currentItem()
        if item is None:
            return
        self.selected_id = str(item.data(QtCore.Qt.UserRole))
        workspace = self.editor.get(self.selected_id)
        self.loading = True
        try:
            self.name_edit.setText(workspace.name)
            self.shortcut_edit.setText(workspace.shortcut)
            self.placements.setRowCount(len(workspace.placements))
            for row, placement in enumerate(workspace.placements):
                values = (
                    placement.name,
                    placement.matcher.process_name,
                    placement.matcher.title_contains,
                    placement.matcher.title_regex,
                    str(placement.monitor_index + 1),
                    _position_text(placement.rect),
                )
                for column, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(value)
                    cell.setData(QtCore.Qt.UserRole, placement.id)
                    if column == 5:
                        cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    self.placements.setItem(row, column, cell)
            self.placements.resizeRowsToContents()
        finally:
            self.loading = False
        self.update_validation()

    def update_validation(self, transient_error: str = "") -> None:
        report = self.editor.validate()
        if transient_error:
            text, state = transient_error, "error"
        elif report.errors:
            text, state = report.errors[0], "error"
        elif report.warnings:
            text, state = report.warnings[0], "warning"
        elif self.editor.is_dirty:
            text, state = "Unsaved workspace changes", "dirty"
        else:
            text, state = "Workspace settings saved", "saved"
        self.status.setText(text)
        self.status.setProperty("status", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.apply_button.setEnabled(report.ok and self.editor.is_dirty)

    def edit_workspace_fields(self) -> None:
        if self.loading or not self.selected_id:
            return
        try:
            self.editor.rename(self.selected_id, self.name_edit.text())
            self.editor.set_shortcut(self.selected_id, self.shortcut_edit.text())
        except ValueError as exc:
            self.update_validation(str(exc))
            return
        self.update_validation()

    def edit_placement(self, item) -> None:
        if self.loading or not self.selected_id or item.column() == 5:
            return
        row = item.row()
        try:
            placement_id = str(self.placements.item(row, 0).data(0x0100))
            self.editor.update_placement(
                self.selected_id,
                placement_id,
                name=self.placements.item(row, 0).text(),
                process_name=self.placements.item(row, 1).text(),
                title_contains=self.placements.item(row, 2).text(),
                title_regex=self.placements.item(row, 3).text(),
                monitor_index=max(0, int(self.placements.item(row, 4).text()) - 1),
            )
        except (TypeError, ValueError) as exc:
            self.update_validation(str(exc))
            return
        self.update_validation()

    def commit(self, close: bool = False) -> bool:
        store = getattr(self.ctx, "config_store", None)
        report = self.editor.commit(
            getattr(store, "save", None),
            self.ctx.apply_settings,
        )
        self.update_validation()
        if not report.ok:
            return False
        if close:
            self.window.hide()
        return True


def show(ctx) -> WorkspaceDialog:
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    existing = getattr(app, "_windows_rectangle_workspaces", None)
    if isinstance(existing, WorkspaceDialog):
        if not existing.editor.is_dirty:
            existing.editor = WorkspaceEditorController(ctx.settings)
            existing.refresh()
        existing.window.show()
        existing.window.raise_()
        existing.window.activateWindow()
        return existing
    dialog = _build(ctx)
    app._windows_rectangle_workspaces = dialog
    dialog.window.show()
    return dialog


def _build(ctx) -> WorkspaceDialog:
    from PySide6 import QtWidgets

    window = QtWidgets.QDialog()
    window.setObjectName("workspaceEditor")
    window.setWindowTitle("Windows Rectangle — Workspaces")
    window.setMinimumSize(940, 620)
    window.resize(1040, 700)
    root = QtWidgets.QVBoxLayout(window)

    title = QtWidgets.QLabel("Workspaces")
    title.setObjectName("workspaceTitle")
    subtitle = QtWidgets.QLabel(
        "Capture windows once, review how each is identified, then restore the layout anytime."
    )
    subtitle.setWordWrap(True)
    root.addWidget(title)
    root.addWidget(subtitle)

    splitter = QtWidgets.QSplitter()
    splitter.setChildrenCollapsible(False)
    left = QtWidgets.QWidget()
    left_layout = QtWidgets.QVBoxLayout(left)
    workspace_list = QtWidgets.QListWidget()
    workspace_list.setObjectName("workspaceList")
    workspace_list.setAccessibleName("Saved workspaces")
    left_layout.addWidget(workspace_list, 1)
    capture = QtWidgets.QPushButton("Capture current windows…")
    capture.setAccessibleName("Capture current windows as a workspace")
    remove = QtWidgets.QPushButton("Delete workspace")
    left_layout.addWidget(capture)
    left_layout.addWidget(remove)

    detail = QtWidgets.QWidget()
    detail_layout = QtWidgets.QVBoxLayout(detail)
    form = QtWidgets.QFormLayout()
    name_edit = QtWidgets.QLineEdit()
    name_edit.setObjectName("workspaceName")
    shortcut_edit = QtWidgets.QLineEdit()
    shortcut_edit.setObjectName("workspaceShortcut")
    shortcut_edit.setPlaceholderText("Optional, for example ctrl+alt+1")
    form.addRow("Name", name_edit)
    form.addRow("Shortcut", shortcut_edit)
    detail_layout.addLayout(form)

    hint = QtWidgets.QLabel(
        "Process + title text is the recommended match. Use regex only for titles that change."
    )
    hint.setWordWrap(True)
    detail_layout.addWidget(hint)
    placements = QtWidgets.QTableWidget()
    placements.setObjectName("workspacePlacements")
    placements.setAccessibleName("Window matching and placement rules")
    placements.setColumnCount(6)
    placements.setHorizontalHeaderLabels(
        ["Window", "Process", "Title contains", "Title regex", "Monitor", "Position"]
    )
    placements.horizontalHeader().setStretchLastSection(True)
    placements.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    detail_layout.addWidget(placements, 1)
    tools = QtWidgets.QHBoxLayout()
    remove_rule = QtWidgets.QPushButton("Remove selected rule")
    test_matches = QtWidgets.QPushButton("Test matches")
    restore = QtWidgets.QPushButton("Restore now")
    tools.addWidget(remove_rule)
    tools.addStretch(1)
    tools.addWidget(test_matches)
    tools.addWidget(restore)
    detail_layout.addLayout(tools)

    splitter.addWidget(left)
    splitter.addWidget(detail)
    splitter.setSizes([250, 750])
    root.addWidget(splitter, 1)

    status = QtWidgets.QLabel()
    status.setObjectName("workspaceStatus")
    buttons = QtWidgets.QDialogButtonBox()
    apply_button = buttons.addButton("Apply", QtWidgets.QDialogButtonBox.ApplyRole)
    save_button = buttons.addButton("Save", QtWidgets.QDialogButtonBox.AcceptRole)
    close_button = buttons.addButton("Close", QtWidgets.QDialogButtonBox.RejectRole)
    footer = QtWidgets.QHBoxLayout()
    footer.addWidget(status, 1)
    footer.addWidget(buttons)
    root.addLayout(footer)

    controller = WorkspaceDialog(
        ctx,
        WorkspaceEditorController(ctx.settings),
        window,
        workspace_list,
        name_edit,
        shortcut_edit,
        placements,
        status,
        apply_button,
    )
    workspace_list.currentItemChanged.connect(lambda *_: controller.load_selected())
    name_edit.editingFinished.connect(controller.edit_workspace_fields)
    shortcut_edit.editingFinished.connect(controller.edit_workspace_fields)
    placements.itemChanged.connect(controller.edit_placement)
    capture.clicked.connect(lambda: _capture(controller, QtWidgets))
    remove.clicked.connect(lambda: _delete_workspace(controller, QtWidgets))
    remove_rule.clicked.connect(lambda: _delete_rule(controller))
    test_matches.clicked.connect(lambda: _test_matches(controller, QtWidgets))
    restore.clicked.connect(lambda: _restore(controller, QtWidgets))
    apply_button.clicked.connect(lambda: controller.commit(False))
    save_button.clicked.connect(lambda: controller.commit(True))
    close_button.clicked.connect(window.hide)
    _apply_style(window)
    controller.refresh()
    return controller


def _capture(controller: WorkspaceDialog, QtWidgets) -> None:
    name, accepted = QtWidgets.QInputDialog.getText(
        controller.window, "Capture Workspace", "Workspace name:"
    )
    if not accepted or not name.strip():
        return
    try:
        workspace = controller.editor.capture(
            cast(WorkspaceWindows, controller.ctx.windows), name.strip()
        )
    except Exception as exc:  # noqa: BLE001
        controller.update_validation(str(exc))
        return
    controller.selected_id = workspace.id
    controller.refresh()


def _delete_workspace(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        return
    workspace = controller.editor.get(controller.selected_id)
    reply = QtWidgets.QMessageBox.question(
        controller.window,
        "Delete workspace",
        f"Delete ‘{workspace.name}’?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    if reply == QtWidgets.QMessageBox.Yes:
        controller.editor.delete_workspace(workspace.id)
        controller.selected_id = ""
        controller.refresh()


def _delete_rule(controller: WorkspaceDialog) -> None:
    row = controller.placements.currentRow()
    if row < 0 or not controller.selected_id:
        return
    item = controller.placements.item(row, 0)
    if item is None:
        return
    controller.editor.delete_placement(controller.selected_id, str(item.data(0x0100)))
    controller.load_selected()


def _test_matches(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        return
    matched, missing = controller.editor.match_counts(
        cast(WorkspaceWindows, controller.ctx.windows), controller.selected_id
    )
    QtWidgets.QMessageBox.information(
        controller.window,
        "Workspace match test",
        f"{matched} matched · {missing} not found. No windows were moved.",
    )


def _restore(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        return
    workspace = controller.editor.get(controller.selected_id)
    result = apply_workspace(cast(WorkspaceWindows, controller.ctx.windows), workspace)
    moved = result.moved
    missing = sum(item.status == "not_found" for item in result.placements)
    blocked = sum(item.status == "blocked" for item in result.placements)
    QtWidgets.QMessageBox.information(
        controller.window,
        "Workspace restored",
        f"{moved} moved · {missing} not found · {blocked} blocked.",
    )


def _position_text(rect) -> str:
    return (
        f"{rect.left / 100:.0f}%, {rect.top / 100:.0f}% — "
        f"{rect.right / 100:.0f}%, {rect.bottom / 100:.0f}%"
    )


def _apply_style(window) -> None:
    window.setStyleSheet(
        """
        QDialog#workspaceEditor { background: #f6f7f9; color: #20242a; }
        QLabel#workspaceTitle { font-size: 22px; font-weight: 600; color: #171a1f; }
        QListWidget, QTableWidget, QLineEdit {
            background: white; border: 1px solid #d0d5dd; border-radius: 6px;
        }
        QListWidget::item { padding: 9px; }
        QListWidget::item:selected { background: #e8f0ff; color: #1849a9; }
        QHeaderView::section { background: #f2f4f7; padding: 7px; border: 0; }
        QLabel#workspaceStatus[status="error"] { color: #b42318; }
        QLabel#workspaceStatus[status="warning"] { color: #8a5a00; }
        QLabel#workspaceStatus[status="saved"] { color: #1f6f43; }
        QLabel#workspaceStatus[status="dirty"] { color: #8a5a00; }
        QPushButton { min-height: 30px; padding: 4px 10px; }
        """
    )
