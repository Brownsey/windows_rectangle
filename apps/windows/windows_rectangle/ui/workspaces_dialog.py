"""Accessible PySide6 editor for captured multi-window workspaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import cast

from ..core.workspace_presets import POSITION_PRESETS, preset_label
from ..core.workspace_service import WorkspaceWindows
from .workspace_canvas import create_layout_canvas
from .workspace_editor import WorkspaceEditorController

_log = logging.getLogger(__name__)


@dataclass(slots=True, weakref_slot=True)
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
                matcher = placement.matcher
                match_parts = [matcher.process_name]
                if matcher.title_contains:
                    match_parts.append(f"title contains “{matcher.title_contains}”")
                if matcher.title_regex:
                    match_parts.append(f"title regex {matcher.title_regex}")
                values = (
                    placement.name,
                    " · ".join(part for part in match_parts if part),
                    placement.launch_command or "Uses an open window",
                    f"Display {placement.monitor_index + 1}",
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
                    cell.setFlags(cell.flags() & ~QtCore.Qt.ItemIsEditable)
                    if column == 5 and placement.id in self.match_results:
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
        elif not self.editor.staged.workspaces:
            text, state = "Create your first layout to get started", "saved"
        elif self.editor.is_dirty:
            text, state = "Unsaved layout changes", "dirty"
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
        self.editor.rebase_onto(self.ctx.settings)
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
    window.setWindowTitle("Windows Rectangle — Layouts")
    window.setMinimumSize(960, 640)
    window.resize(1180, 780)
    root = QtWidgets.QVBoxLayout(window)

    title = QtWidgets.QLabel("Custom Layouts")
    title.setObjectName("workspaceTitle")
    subtitle = QtWidgets.QLabel(
        "Launch and position any mix of apps or named accounts with one shortcut. "
        "Match each window by app and title, then drag it to the exact place you want."
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
    workspace_list.setAccessibleName("Saved layouts")
    left_layout.addWidget(workspace_list, 1)
    template = QtWidgets.QPushButton("Use a Template…")
    template.setAccessibleName("Create a layout from a template")
    create = QtWidgets.QPushButton("New Layout")
    create.setAccessibleName("Create an empty layout")
    capture = QtWidgets.QPushButton("Capture Open Apps…")
    capture.setAccessibleName("Capture open apps as a layout")
    duplicate = QtWidgets.QPushButton("Duplicate Layout")
    remove = QtWidgets.QPushButton("Delete Layout")
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
    shortcut_edit.setPlaceholderText("For example Ctrl+Alt+1")
    form.addRow("Layout name", name_edit)
    form.addRow("Launch shortcut", shortcut_edit)
    detail_layout.addLayout(form)

    hint = QtWidgets.QLabel(
        "Tip: use the account or document name from the window title to distinguish several "
        "copies of the same app."
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
    placements.setAccessibleName("Apps in this layout")
    placements.setToolTip("Select an app to edit its matching, launch, display, or position")
    placements.setColumnCount(6)
    placements.setHorizontalHeaderLabels(
        [
            "App or account",
            "Window match",
            "Launch",
            "Display",
            "Position",
            "Status",
        ]
    )
    header = placements.horizontalHeader()
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
    header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
    header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
    header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
    placements.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    detail_layout.addWidget(placements, 1)
    edit_tools = QtWidgets.QHBoxLayout()
    add_rule = QtWidgets.QPushButton("Add App…")
    edit_rule = QtWidgets.QPushButton("Edit App…")
    remove_rule = QtWidgets.QPushButton("Remove App")
    choose_position = QtWidgets.QPushButton("Choose Position…")
    edit_tools.addWidget(add_rule)
    edit_tools.addWidget(edit_rule)
    edit_tools.addWidget(remove_rule)
    edit_tools.addWidget(choose_position)
    edit_tools.addStretch(1)
    detail_layout.addLayout(edit_tools)

    actions = QtWidgets.QHBoxLayout()
    record_positions = QtWidgets.QPushButton("Record current positions")
    record_positions.setToolTip(
        "Learn the exact size, position, and monitor of each matching open window"
    )
    test_matches = QtWidgets.QPushButton("Test matches")
    restore = QtWidgets.QPushButton("Launch & Arrange")
    restore.setObjectName("primaryAction")
    actions.addWidget(record_positions)
    actions.addWidget(test_matches)
    actions.addStretch(1)
    actions.addWidget(restore)
    detail_layout.addLayout(actions)

    splitter.addWidget(left)
    splitter.addWidget(detail)
    splitter.setSizes([230, 950])
    root.addWidget(splitter, 1)

    status = QtWidgets.QLabel()
    status.setObjectName("workspaceStatus")
    buttons = QtWidgets.QDialogButtonBox()
    apply_button = buttons.addButton("Save Changes", QtWidgets.QDialogButtonBox.ApplyRole)
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
    placements.itemSelectionChanged.connect(lambda: _table_selected(controller))
    placements.cellDoubleClicked.connect(lambda *_: _edit_application(controller, QtWidgets))
    template.clicked.connect(lambda: _create_from_template(controller, QtWidgets))
    create.clicked.connect(lambda: _create_empty(controller, QtWidgets))
    capture.clicked.connect(lambda: _capture(controller, QtWidgets))
    duplicate.clicked.connect(lambda: _duplicate_workspace(controller))
    remove.clicked.connect(lambda: _delete_workspace(controller, QtWidgets))
    add_rule.clicked.connect(lambda: _add_application(controller, QtWidgets))
    edit_rule.clicked.connect(lambda: _edit_application(controller, QtWidgets))
    remove_rule.clicked.connect(lambda: _delete_rule(controller, QtWidgets))
    choose_position.clicked.connect(
        lambda: _choose_position(controller, controller.placements.currentRow(), QtWidgets)
    )
    record_positions.clicked.connect(lambda: _record_positions(controller, QtWidgets))
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
        controller.update_validation("Select a layout to duplicate")
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
        "Unsaved layout changes",
        "Save your layout changes before closing?",
        QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
        QtWidgets.QMessageBox.Save,
    )
    if choice == QtWidgets.QMessageBox.Save:
        controller.commit(True)
    elif choice == QtWidgets.QMessageBox.Discard:
        controller.editor = WorkspaceEditorController(controller.ctx.settings)
        controller.window.hide()


def _create_empty(controller: WorkspaceDialog, QtWidgets) -> None:
    name, accepted = QtWidgets.QInputDialog.getText(controller.window, "New Layout", "Layout name:")
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
        controller.update_validation("Create or select a layout first")
        return
    values = _application_rule_dialog(controller, QtWidgets)
    if values is None:
        return
    try:
        controller.editor.add_placement(controller.selected_id, **values)
    except ValueError as exc:
        controller.update_validation(str(exc))
        return
    controller.load_selected()
    controller.autosave("App saved to layout")


def _edit_application(controller: WorkspaceDialog, QtWidgets) -> None:
    row = controller.placements.currentRow()
    if row < 0 or not controller.selected_id:
        controller.update_validation("Select an app to edit")
        return
    item = controller.placements.item(row, 0)
    if item is None:
        return
    workspace = controller.editor.get(controller.selected_id)
    placement_id = str(item.data(0x0100))
    placement = next(entry for entry in workspace.placements if entry.id == placement_id)
    values = _application_rule_dialog(controller, QtWidgets, placement)
    if values is None:
        return
    preset_id = values.pop("preset_id")
    try:
        controller.editor.update_placement(
            controller.selected_id,
            placement_id,
            **values,
        )
        if preset_id:
            controller.editor.set_placement_preset(controller.selected_id, placement_id, preset_id)
    except ValueError as exc:
        controller.update_validation(str(exc))
        return
    controller.load_selected()
    controller.autosave("App changes saved")


def _application_rule_dialog(controller: WorkspaceDialog, QtWidgets, placement=None):
    dialog = QtWidgets.QDialog(controller.window)
    dialog.setWindowTitle("Edit App" if placement is not None else "Add App")
    dialog.setMinimumWidth(560)
    form = QtWidgets.QFormLayout(dialog)
    name = QtWidgets.QLineEdit()
    name.setAccessibleName("App or account name")
    process = QtWidgets.QLineEdit()
    process.setPlaceholderText("For example RuneLite.exe or chrome.exe")
    process.setAccessibleName("Application process")
    title = QtWidgets.QLineEdit()
    title.setPlaceholderText("For example Alice, Outlook, or ChatGPT")
    title.setAccessibleName("Window title contains")
    title_regex = QtWidgets.QLineEdit()
    title_regex.setPlaceholderText("Optional advanced regular expression")
    launch = QtWidgets.QLineEdit()
    launch.setPlaceholderText("Optional executable path and arguments")
    launch.setAccessibleName("Launch command")
    browse = QtWidgets.QPushButton("Browse…")

    def browse_executable() -> None:
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            dialog,
            "Choose Application",
            "",
            "Applications (*.exe);;All Files (*)",
        )
        if path:
            launch.setText(f'"{path}"')

    browse.clicked.connect(browse_executable)
    launch_row = QtWidgets.QWidget()
    launch_layout = QtWidgets.QHBoxLayout(launch_row)
    launch_layout.setContentsMargins(0, 0, 0, 0)
    launch_layout.addWidget(launch, 1)
    launch_layout.addWidget(browse)
    monitor = QtWidgets.QSpinBox()
    monitor.setRange(1, 32)
    position = QtWidgets.QComboBox()
    if placement is not None and all(placement.rect != preset.rect for preset in POSITION_PRESETS):
        position.addItem("Custom — keep canvas position", "")
    for preset in POSITION_PRESETS:
        position.addItem(preset.label, preset.id)
    if placement is not None:
        name.setText(placement.name)
        process.setText(placement.matcher.process_name)
        title.setText(placement.matcher.title_contains)
        title_regex.setText(placement.matcher.title_regex)
        launch.setText(placement.launch_command)
        monitor.setValue(placement.monitor_index + 1)
        for preset in POSITION_PRESETS:
            if placement.rect == preset.rect:
                position.setCurrentIndex(position.findData(preset.id))
                break
    form.addRow("Name", name)
    form.addRow("Process", process)
    form.addRow("Window title contains", title)
    form.addRow("Title regex", title_regex)
    form.addRow("Launch command", launch_row)
    form.addRow("Display", monitor)
    form.addRow("Starting position", position)
    help_text = QtWidgets.QLabel(
        "For several copies of one app, give each rule a different window-title match. "
        "Add a launch command when this layout should open the app if it is missing."
    )
    help_text.setWordWrap(True)
    form.addRow(help_text)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    name.setFocus()
    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return None
    return {
        "name": name.text(),
        "process_name": process.text(),
        "title_contains": title.text(),
        "title_regex": title_regex.text(),
        "launch_command": launch.text(),
        "monitor_index": monitor.value() - 1,
        "preset_id": str(position.currentData()),
    }


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
        controller.window, "Capture Open Apps", "Layout name:"
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
        "Delete layout",
        f"Delete ‘{workspace.name}’?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    if reply == QtWidgets.QMessageBox.Yes:
        controller.editor.delete_workspace(workspace.id)
        controller.selected_id = ""
        controller.refresh()
        controller.autosave("Workspace deleted")


def _delete_rule(controller: WorkspaceDialog, QtWidgets) -> None:
    row = controller.placements.currentRow()
    if row < 0 or not controller.selected_id:
        return
    item = controller.placements.item(row, 0)
    if item is None:
        return
    reply = QtWidgets.QMessageBox.question(
        controller.window,
        "Remove app",
        f"Remove ‘{item.text()}’ from this layout?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    if reply != QtWidgets.QMessageBox.Yes:
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


def _record_positions(controller: WorkspaceDialog, QtWidgets) -> None:
    if not controller.selected_id:
        controller.update_validation("Select a layout first")
        return
    reply = QtWidgets.QMessageBox.question(
        controller.window,
        "Record current positions",
        "Replace the saved positions for every matching open app?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    if reply != QtWidgets.QMessageBox.Yes:
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
    if controller.editor.is_dirty and not controller.autosave("Layout saved"):
        return
    try:
        queued = controller.ctx.queue_workspace(controller.selected_id)
    except Exception as exc:  # noqa: BLE001
        controller.update_validation(f"Could not launch layout: {exc}")
        return
    if queued:
        controller.status.setText("Launching apps and waiting for their windows…")
        controller.status.setProperty("status", "dirty")
    else:
        controller.status.setText("This layout is already being launched")
        controller.status.setProperty("status", "warning")


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
        QPushButton#primaryAction {
            background: #175cd3; color: white; border: 1px solid #175cd3;
            border-radius: 6px; font-weight: 600; padding: 5px 16px;
        }
        QPushButton#primaryAction:hover { background: #1849a9; }
        QPushButton#primaryAction:pressed { background: #153f82; }
        """
    )
