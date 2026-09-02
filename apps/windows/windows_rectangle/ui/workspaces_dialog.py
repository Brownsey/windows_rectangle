"""Accessible PySide6 editor for captured multi-window workspaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import cast

from ..core.workspace_presets import POSITION_PRESETS, preset_label
from ..core.workspace_service import WorkspaceWindows, apply_workspace
from .workspace_canvas import create_layout_canvas
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
    canvas: object
    status: object
    apply_button: object
    selected_id: str = ""
    loading: bool = False
    match_results: dict[str, bool] = field(default_factory=dict)

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
                self.canvas.set_placements(())
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
                    preset_label(placement.rect),
                    (
                        "Matched"
                        if self.match_results.get(placement.id) is True
                        else "Not found"
                        if self.match_results.get(placement.id) is False
                        else "Not tested"
                    ),
                )
                for column, value in enumerate(values):
                    cell = QtWidgets.QTableWidgetItem(value)
                    cell.setData(QtCore.Qt.UserRole, placement.id)
                    if column >= 5:
                        cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    if column == 6 and placement.id in self.match_results:
                        cell.setForeground(
                            QtCore.Qt.darkGreen
                            if self.match_results[placement.id]
                            else QtCore.Qt.red
                        )
                    self.placements.setItem(row, column, cell)
            self.placements.resizeRowsToContents()
            self.canvas.set_placements(workspace.placements)
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
            text, state = "All changes saved automatically", "saved"
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
        self.autosave()

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
        self.autosave()

    def autosave(self, success_text: str = "Saved automatically") -> bool:
        store = getattr(self.ctx, "config_store", None)
        outcome = self.editor.autosave(
            getattr(store, "save", None),
            self.ctx.apply_settings,
        )
        if outcome.error:
            self.update_validation(f"Autosave failed: {outcome.error}")
            return False
        if not outcome.saved:
            self.update_validation()
            return False
        self.update_validation()
        self.status.setText(success_text)
        self.status.setProperty("status", "saved")
        return True

    def commit(self, close: bool = False) -> bool:
        if not self.autosave("Saved"):
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
        "Capture open windows, start from a template, or add applications by name. "
        "Drag cards to arrange them, then restore the setup with one shortcut."
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
    template = QtWidgets.QPushButton("Start from template…")
    template.setAccessibleName("Create a workspace from a template")
    create = QtWidgets.QPushButton("New empty workspace")
    create.setAccessibleName("Create an empty workspace")
    capture = QtWidgets.QPushButton("Capture current windows…")
    capture.setAccessibleName("Capture current windows as a workspace")
    duplicate = QtWidgets.QPushButton("Duplicate workspace")
    remove = QtWidgets.QPushButton("Delete workspace")
    left_layout.addWidget(template)
    left_layout.addWidget(create)
    left_layout.addWidget(capture)
    left_layout.addWidget(duplicate)
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
    canvas = create_layout_canvas(
        lambda placement_id, rect: _canvas_moved(controller, placement_id, rect),
        lambda placement_id: _canvas_selected(controller, placement_id),
    )
    detail_layout.addWidget(canvas)
    placements = QtWidgets.QTableWidget()
    placements.setObjectName("workspacePlacements")
    placements.setAccessibleName("Window matching and placement rules")
    placements.setToolTip("Double-click Position to choose a preset")
    placements.setColumnCount(7)
    placements.setHorizontalHeaderLabels(
        [
            "Window",
            "Process",
            "Title contains",
            "Title regex",
            "Monitor",
            "Position",
            "Match status",
        ]
    )
    placements.horizontalHeader().setStretchLastSection(True)
    placements.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    detail_layout.addWidget(placements, 1)
    tools = QtWidgets.QHBoxLayout()
    add_rule = QtWidgets.QPushButton("Add application…")
    remove_rule = QtWidgets.QPushButton("Remove selected rule")
    record_positions = QtWidgets.QPushButton("Record current positions")
    record_positions.setToolTip(
        "Learn the exact size, position, and monitor of each matching open window"
    )
    test_matches = QtWidgets.QPushButton("Test matches")
    restore = QtWidgets.QPushButton("Restore now")
    tools.addWidget(add_rule)
    tools.addWidget(remove_rule)
    tools.addStretch(1)
    tools.addWidget(record_positions)
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
    apply_button = buttons.addButton("Save now", QtWidgets.QDialogButtonBox.ApplyRole)
    close_button = buttons.addButton("Done", QtWidgets.QDialogButtonBox.AcceptRole)
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
        canvas,
        status,
        apply_button,
    )
    workspace_list.currentItemChanged.connect(lambda *_: controller.load_selected())
    name_edit.editingFinished.connect(controller.edit_workspace_fields)
    shortcut_edit.editingFinished.connect(controller.edit_workspace_fields)
    placements.itemChanged.connect(controller.edit_placement)
    placements.itemSelectionChanged.connect(lambda: _table_selected(controller))
    placements.cellDoubleClicked.connect(
        lambda row, column: _choose_position(controller, row, QtWidgets) if column == 5 else None
    )
    template.clicked.connect(lambda: _create_from_template(controller, QtWidgets))
    create.clicked.connect(lambda: _create_empty(controller, QtWidgets))
    capture.clicked.connect(lambda: _capture(controller, QtWidgets))
    duplicate.clicked.connect(lambda: _duplicate_workspace(controller))
    remove.clicked.connect(lambda: _delete_workspace(controller, QtWidgets))
    add_rule.clicked.connect(lambda: _add_application(controller, QtWidgets))
    remove_rule.clicked.connect(lambda: _delete_rule(controller))
    record_positions.clicked.connect(lambda: _record_positions(controller))
    test_matches.clicked.connect(lambda: _test_matches(controller, QtWidgets))
    restore.clicked.connect(lambda: _restore(controller, QtWidgets))
    apply_button.clicked.connect(lambda: controller.commit(False))
    close_button.clicked.connect(lambda: _close(controller, QtWidgets))
    _apply_style(window)
    controller.refresh()
    return controller


def _table_selected(controller: WorkspaceDialog) -> None:
    row = controller.placements.currentRow()
    if row < 0:
        return
    item = controller.placements.item(row, 0)
    if item is not None:
        controller.canvas.select(str(item.data(0x0100)))


def _canvas_selected(controller: WorkspaceDialog, placement_id: str) -> None:
    for row in range(controller.placements.rowCount()):
        item = controller.placements.item(row, 0)
        if item is not None and str(item.data(0x0100)) == placement_id:
            controller.placements.selectRow(row)
            return


def _canvas_moved(controller: WorkspaceDialog, placement_id: str, rect) -> None:
    if not controller.selected_id:
        return
    controller.editor.set_placement_rect(controller.selected_id, placement_id, rect)
    controller.load_selected()
    _canvas_selected(controller, placement_id)
    controller.autosave("Custom position saved automatically")


def _create_from_template(controller: WorkspaceDialog, QtWidgets) -> None:
    choices = ["Office — Slack, Outlook, Chrome", "RuneScape — account grid"]
    selected, accepted = QtWidgets.QInputDialog.getItem(
        controller.window, "Workspace template", "Choose a starting layout:", choices, 0, False
    )
    if not accepted:
        return
    try:
        if selected == choices[0]:
            workspace = controller.editor.add_office_template()
        else:
            accounts, accepted = QtWidgets.QInputDialog.getMultiLineText(
                controller.window,
                "RuneScape accounts",
                "Enter one account/window title per line:",
            )
            if not accepted:
                return
            workspace = controller.editor.add_runescape_template(accounts.splitlines())
    except ValueError as exc:
        controller.update_validation(str(exc))
        return
    controller.selected_id = workspace.id
    controller.match_results.clear()
    controller.refresh()
    controller.autosave("Template saved automatically")


def _duplicate_workspace(controller: WorkspaceDialog) -> None:
    if not controller.selected_id:
        controller.update_validation("Select a workspace to duplicate")
        return
    workspace = controller.editor.duplicate(controller.selected_id)
    controller.selected_id = workspace.id
    controller.match_results.clear()
    controller.refresh()
    controller.autosave("Duplicate saved automatically")


def _close(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.editor.is_dirty:
        controller.window.hide()
        return
    choice = QtWidgets.QMessageBox.warning(
        controller.window,
        "Unsaved workspace changes",
        "Save your workspace changes before closing?",
        QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Save,
    )
    if choice == QtWidgets.QMessageBox.Save:
        controller.commit(True)
    elif choice == QtWidgets.QMessageBox.Discard:
        controller.editor = WorkspaceEditorController(controller.ctx.settings)
        controller.window.hide()


def _create_empty(controller: WorkspaceDialog, QtWidgets) -> None:
    name, accepted = QtWidgets.QInputDialog.getText(
        controller.window, "New Workspace", "Workspace name:"
    )
    if not accepted or not name.strip():
        return
    try:
        workspace = controller.editor.create(name)
    except ValueError as exc:
        controller.update_validation(str(exc))
        return
    controller.selected_id = workspace.id
    controller.refresh()
    controller.autosave("Workspace saved automatically")


def _add_application(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        controller.update_validation("Create or select a workspace first")
        return
    dialog = QtWidgets.QDialog(controller.window)
    dialog.setWindowTitle("Add application rule")
    form = QtWidgets.QFormLayout(dialog)
    name = QtWidgets.QLineEdit()
    process = QtWidgets.QLineEdit()
    process.setPlaceholderText("For example RuneLite.exe or chrome.exe")
    title = QtWidgets.QLineEdit()
    title.setPlaceholderText("Optional account, document, or window name")
    monitor = QtWidgets.QSpinBox()
    monitor.setRange(1, 32)
    position = QtWidgets.QComboBox()
    for preset in POSITION_PRESETS:
        position.addItem(preset.label, preset.id)
    form.addRow("Rule name", name)
    form.addRow("Application process", process)
    form.addRow("Window title contains", title)
    form.addRow("Monitor", monitor)
    form.addRow("Position", position)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    name.setFocus()
    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return
    try:
        controller.editor.add_placement(
            controller.selected_id,
            name=name.text(),
            process_name=process.text(),
            title_contains=title.text(),
            monitor_index=monitor.value() - 1,
            preset_id=str(position.currentData()),
        )
    except ValueError as exc:
        controller.update_validation(str(exc))
        return
    controller.load_selected()
    controller.autosave("Application rule saved automatically")


def _choose_position(controller: WorkspaceDialog, row: int, QtWidgets) -> None:
    if not controller.selected_id:
        return
    item = controller.placements.item(row, 0)
    if item is None:
        return
    labels = [preset.label for preset in POSITION_PRESETS]
    selected, accepted = QtWidgets.QInputDialog.getItem(
        controller.window, "Choose position", "Position preset:", labels, 0, False
    )
    if not accepted:
        return
    preset = POSITION_PRESETS[labels.index(selected)]
    controller.editor.set_placement_preset(
        controller.selected_id, str(item.data(0x0100)), preset.id
    )
    controller.load_selected()
    controller.autosave("Position saved automatically")


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
    controller.autosave("Captured workspace saved automatically")


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
        controller.autosave("Workspace deleted")


def _delete_rule(controller: WorkspaceDialog) -> None:
    row = controller.placements.currentRow()
    if row < 0 or not controller.selected_id:
        return
    item = controller.placements.item(row, 0)
    if item is None:
        return
    controller.editor.delete_placement(controller.selected_id, str(item.data(0x0100)))
    controller.load_selected()
    controller.autosave("Application rule removed")


def _test_matches(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        return
    controller.match_results = controller.editor.match_results(
        cast(WorkspaceWindows, controller.ctx.windows), controller.selected_id
    )
    matched = sum(controller.match_results.values())
    missing = len(controller.match_results) - matched
    controller.load_selected()
    controller.status.setText(f"{matched} matched · {missing} not found. No windows moved.")
    controller.status.setProperty("status", "saved" if not missing else "warning")


def _record_positions(controller: WorkspaceDialog) -> None:
    if not controller.selected_id:
        controller.update_validation("Select a workspace first")
        return
    result = controller.editor.record_current_positions(
        cast(WorkspaceWindows, controller.ctx.windows), controller.selected_id
    )
    controller.load_selected()
    message = f"Recorded {result.updated} current window position(s)"
    if result.not_found:
        message += f" · {len(result.not_found)} not found and left unchanged"
    controller.status.setText(message)
    controller.status.setProperty("status", "warning" if result.not_found else "dirty")
    controller.autosave(message + " · saved automatically")


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
