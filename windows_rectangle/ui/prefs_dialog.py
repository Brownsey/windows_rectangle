"""PySide6 Preferences dialog (brief §2 #15).

Thin Qt skin over `ui.preferences.PrefsController`. Only handles widget
construction + signal wiring; all validation, conflict detection, and
commit logic live in the controller (which is unit-tested without Qt).

This module is lazy-imported by `open_prefs_window` so the prefs
controller (and tests that exercise it via a fake dialog factory) can
live without PySide6 at import time.

Layout:
    [General]
      Gap            [QSpinBox 0..256]
      Drag-to-edge   [QCheckBox]
      Launch at login[QCheckBox]
      Almost-max %   [QDoubleSpinBox 0.1..1.0 step 0.05]
      Cycle timeout  [QDoubleSpinBox 0..10 step 0.1]
    [Shortcuts]
      Action            Current combo            (one row per action,
                        [QLineEdit]                editable text — power
                                                   users can type combos
                                                   like "ctrl+alt+left")
    [Validation panel]   shows live errors + warnings
    [ OK ] [ Cancel ]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .preferences import PrefsController


_log = logging.getLogger(__name__)


def build_dialog(pc: PrefsController):
    """Construct and return the QDialog. Caller invokes `.exec()`.

    The returned dialog is wired so that:
      - Edits stage into `pc` immediately.
      - The validation panel refreshes on every change.
      - OK is disabled while there are errors.
      - On accept, the caller (`open_prefs_window`) calls `pc.commit`.
    """
    from PySide6 import QtCore, QtWidgets  # noqa: PLC0415 — lazy by design

    from ..core.actions import Action
    from .preferences import (
        ALMOST_MAX_MAX,
        ALMOST_MAX_MIN,
        CYCLE_TIMEOUT_MAX,
        CYCLE_TIMEOUT_MIN,
        GAP_MAX,
        GAP_MIN,
        ShortcutParseError,
    )

    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle("Windows Rectangle — Preferences")
    dlg.setModal(True)
    root = QtWidgets.QVBoxLayout(dlg)

    # ----- General tab ------------------------------------------------
    general = QtWidgets.QFormLayout()

    gap_spin = QtWidgets.QSpinBox()
    gap_spin.setRange(GAP_MIN, GAP_MAX)
    gap_spin.setValue(pc.staged.gap)
    gap_spin.setSuffix(" px")
    gap_spin.valueChanged.connect(pc.set_gap)

    drag_box = QtWidgets.QCheckBox("Drag windows to screen edges to snap")
    drag_box.setChecked(pc.staged.drag_to_edge_enabled)
    drag_box.toggled.connect(pc.set_drag_to_edge_enabled)

    launch_box = QtWidgets.QCheckBox("Launch at login")
    launch_box.setChecked(pc.staged.launch_at_login)
    launch_box.toggled.connect(pc.set_launch_at_login)

    almost_spin = QtWidgets.QDoubleSpinBox()
    almost_spin.setRange(ALMOST_MAX_MIN, ALMOST_MAX_MAX)
    almost_spin.setSingleStep(0.05)
    almost_spin.setDecimals(2)
    almost_spin.setValue(pc.staged.almost_maximize_scale)
    almost_spin.valueChanged.connect(pc.set_almost_maximize_scale)

    cycle_spin = QtWidgets.QDoubleSpinBox()
    cycle_spin.setRange(CYCLE_TIMEOUT_MIN, CYCLE_TIMEOUT_MAX)
    cycle_spin.setSingleStep(0.1)
    cycle_spin.setDecimals(1)
    cycle_spin.setValue(pc.staged.cycle_idle_timeout)
    cycle_spin.setSuffix(" s")
    cycle_spin.valueChanged.connect(pc.set_cycle_idle_timeout)

    general.addRow("Gap between tiled windows", gap_spin)
    general.addRow("", drag_box)
    general.addRow("", launch_box)
    general.addRow("Almost-maximize scale", almost_spin)
    general.addRow("Repeat-key cycle timeout", cycle_spin)

    general_group = QtWidgets.QGroupBox("General")
    general_group.setLayout(general)
    root.addWidget(general_group)

    # ----- Shortcuts table --------------------------------------------
    shortcuts_table = QtWidgets.QTableWidget()
    shortcuts_table.setColumnCount(2)
    shortcuts_table.setHorizontalHeaderLabels(["Action", "Shortcut"])
    shortcuts_table.horizontalHeader().setStretchLastSection(True)
    shortcuts_table.verticalHeader().setVisible(False)
    shortcuts_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
    shortcuts_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

    actions_list = list(Action)
    shortcuts_table.setRowCount(len(actions_list))
    for row, action in enumerate(actions_list):
        name_item = QtWidgets.QTableWidgetItem(action.value)
        name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
        shortcuts_table.setItem(row, 0, name_item)
        current = pc.staged.shortcuts.get(action, "")
        shortcuts_table.setItem(row, 1, QtWidgets.QTableWidgetItem(current))

    # ----- Validation panel -------------------------------------------
    validation = QtWidgets.QLabel()
    validation.setWordWrap(True)
    validation.setStyleSheet("color: #b22; padding: 4px;")

    # ----- Buttons ----------------------------------------------------
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    ok_btn = buttons.button(QtWidgets.QDialogButtonBox.Ok)

    def refresh_validation():
        report = pc.validate()
        ok_btn.setEnabled(report.ok)
        lines: list[str] = []
        if report.errors:
            lines.extend(f"⛔ {e}" for e in report.errors)
        if report.warnings:
            lines.extend(f"⚠ {w}" for w in report.warnings)
        validation.setText("\n".join(lines))

    def on_table_change(item):
        if item.column() != 1:
            return
        action = actions_list[item.row()]
        text = item.text().strip()
        try:
            if text:
                pc.set_shortcut(action, text)
            else:
                pc.clear_shortcut(action)
        except ShortcutParseError as e:
            _log.debug("shortcut parse failed", exc_info=True)
            validation.setText(f"⛔ {action.value}: {e}")
            ok_btn.setEnabled(False)
            return
        refresh_validation()

    shortcuts_table.itemChanged.connect(on_table_change)
    gap_spin.valueChanged.connect(lambda *_: refresh_validation())
    drag_box.toggled.connect(lambda *_: refresh_validation())
    launch_box.toggled.connect(lambda *_: refresh_validation())
    almost_spin.valueChanged.connect(lambda *_: refresh_validation())
    cycle_spin.valueChanged.connect(lambda *_: refresh_validation())

    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)

    # "Reset shortcuts" wipes staged shortcuts back to DEFAULT_SHORTCUTS
    # then repaints the table from `pc.staged.shortcuts`. We toggle the
    # itemChanged signal off while re-populating so the change-callback
    # doesn't fire 22× and re-stage what we just reset.
    reset_btn = QtWidgets.QPushButton("Reset shortcuts to defaults")

    def on_reset_shortcuts():
        pc.reset_shortcuts_to_defaults()
        shortcuts_table.blockSignals(True)
        try:
            for row, action in enumerate(actions_list):
                combo = pc.staged.shortcuts.get(action, "")
                # Replace text rather than the QTableWidgetItem object
                # so any UI styling the user/Qt applied is preserved.
                shortcuts_table.item(row, 1).setText(combo)
        finally:
            shortcuts_table.blockSignals(False)
        refresh_validation()

    reset_btn.clicked.connect(on_reset_shortcuts)

    shortcuts_group = QtWidgets.QGroupBox("Shortcuts")
    sg_layout = QtWidgets.QVBoxLayout(shortcuts_group)
    sg_layout.addWidget(shortcuts_table)
    sg_layout.addWidget(reset_btn, alignment=QtCore.Qt.AlignRight)
    root.addWidget(shortcuts_group)
    root.addWidget(validation)
    root.addWidget(buttons)

    refresh_validation()
    dlg.resize(560, 580)
    return dlg
