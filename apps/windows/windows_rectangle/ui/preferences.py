"""Preferences window for editable settings and shortcut bindings.

Qt imports stay inside `show()`/builder helpers so this module remains importable
in test and headless environments.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..core.actions import DEFAULT_SHORTCUTS, Action
from ..core.keymap import UnsupportedKeyError, translate
from ..core.shortcuts import ShortcutParseError, is_reserved, parse
from ..ports.config_store import Settings
from .logo import build_qicon

if TYPE_CHECKING:
    from ..app import AppContext


_log = logging.getLogger(__name__)


ACTION_GROUPS: tuple[tuple[str, tuple[Action, ...]], ...] = (
    (
        "Halves",
        (
            Action.LEFT_HALF,
            Action.RIGHT_HALF,
            Action.TOP_HALF,
            Action.BOTTOM_HALF,
        ),
    ),
    (
        "Quarters",
        (
            Action.TOP_LEFT_QUARTER,
            Action.TOP_RIGHT_QUARTER,
            Action.BOTTOM_LEFT_QUARTER,
            Action.BOTTOM_RIGHT_QUARTER,
        ),
    ),
    (
        "Sixths",
        (
            Action.TOP_LEFT_SIXTH,
            Action.TOP_RIGHT_SIXTH,
            Action.BOTTOM_LEFT_SIXTH,
            Action.BOTTOM_RIGHT_SIXTH,
        ),
    ),
    (
        "Thirds",
        (
            Action.FIRST_THIRD,
            Action.CENTER_THIRD,
            Action.LAST_THIRD,
            Action.FIRST_TWO_THIRDS,
            Action.LAST_TWO_THIRDS,
        ),
    ),
    (
        "Window",
        (
            Action.MAXIMIZE,
            Action.MAXIMIZE_HEIGHT,
            Action.ALMOST_MAXIMIZE,
            Action.CENTER,
            Action.LARGER,
            Action.SMALLER,
            Action.RESTORE,
        ),
    ),
    (
        "Displays",
        (
            Action.NEXT_DISPLAY,
            Action.PREV_DISPLAY,
        ),
    ),
)

_ACTION_LABELS: dict[Action, str] = {
    Action.LEFT_HALF: "Left Half",
    Action.RIGHT_HALF: "Right Half",
    Action.TOP_HALF: "Top Half",
    Action.BOTTOM_HALF: "Bottom Half",
    Action.TOP_LEFT_QUARTER: "Top Left",
    Action.TOP_RIGHT_QUARTER: "Top Right",
    Action.BOTTOM_LEFT_QUARTER: "Bottom Left",
    Action.BOTTOM_RIGHT_QUARTER: "Bottom Right",
    Action.TOP_LEFT_SIXTH: "Top Left 1/6",
    Action.TOP_RIGHT_SIXTH: "Top Right 3/6",
    Action.BOTTOM_LEFT_SIXTH: "Bottom Left 4/6",
    Action.BOTTOM_RIGHT_SIXTH: "Bottom Right 6/6",
    Action.FIRST_THIRD: "Left Third",
    Action.CENTER_THIRD: "Middle Third",
    Action.LAST_THIRD: "Right Third",
    Action.FIRST_TWO_THIRDS: "First Two Thirds",
    Action.LAST_TWO_THIRDS: "Last Two Thirds",
    Action.MAXIMIZE: "Maximize",
    Action.MAXIMIZE_HEIGHT: "Maximize Height",
    Action.ALMOST_MAXIMIZE: "Middle Majority",
    Action.CENTER: "Center",
    Action.LARGER: "Larger",
    Action.SMALLER: "Smaller",
    Action.RESTORE: "Restore",
    Action.NEXT_DISPLAY: "Next Display",
    Action.PREV_DISPLAY: "Previous Display",
}

_QT_MODIFIERS = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Meta",
}

_QT_KEYS = {
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "enter": "Return",
    "backspace": "Backspace",
    "delete": "Del",
    "insert": "Ins",
    "escape": "Esc",
    "space": "Space",
    "pageup": "PgUp",
    "pagedown": "PgDown",
}

_DISPLAY_MODIFIERS = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
}

_DISPLAY_KEYS = {
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "enter": "Enter",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "escape": "Esc",
    "space": "Space",
    "pageup": "Pg Up",
    "pagedown": "Pg Down",
}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class PreferencesController:
    ctx: AppContext
    window: object
    shortcut_widgets: dict[Action, object] = field(default_factory=dict)
    gap_spin: object | None = None
    cycle_spin: object | None = None
    almost_spin: object | None = None
    drag_checkbox: object | None = None
    launch_checkbox: object | None = None
    status_label: object | None = None
    save_button: object | None = None
    apply_button: object | None = None
    dirty: bool = False
    _loading: bool = False

    def collect_settings(self) -> Settings:
        shortcuts = dict(self.ctx.settings.shortcuts)
        for action, widget in self.shortcut_widgets.items():
            shortcuts[action] = _sequence_text(widget)

        return Settings(
            shortcuts=shortcuts,
            gap=int(self.gap_spin.value()) if self.gap_spin is not None else self.ctx.settings.gap,
            launch_at_login=(
                bool(self.launch_checkbox.isChecked())
                if self.launch_checkbox is not None
                else self.ctx.settings.launch_at_login
            ),
            cycle_idle_timeout=(
                float(self.cycle_spin.value())
                if self.cycle_spin is not None
                else self.ctx.settings.cycle_idle_timeout
            ),
            drag_to_edge_enabled=(
                bool(self.drag_checkbox.isChecked())
                if self.drag_checkbox is not None
                else self.ctx.settings.drag_to_edge_enabled
            ),
            almost_maximize_scale=(
                float(self.almost_spin.value()) / 100.0
                if self.almost_spin is not None
                else self.ctx.settings.almost_maximize_scale
            ),
        )

    def refresh_from_context(self) -> None:
        self._loading = True
        try:
            _load_settings_into_widgets(self, self.ctx.settings)
        finally:
            self._loading = False
        self.dirty = False
        self.update_validation()

    def mark_dirty(self) -> None:
        if self._loading:
            return
        self.dirty = True
        self.update_validation()

    def update_validation(self) -> ValidationResult:
        result = validate_shortcuts(self.collect_settings().shortcuts)
        if self.status_label is not None:
            if result.errors:
                self.status_label.setText(f"Fix required: {result.errors[0]}")
                _set_widget_property(self.status_label, "status", "error")
            elif result.warnings:
                self.status_label.setText(f"Warning: {result.warnings[0]}")
                _set_widget_property(self.status_label, "status", "warning")
            else:
                self.status_label.setText(
                    _status_text(self.dirty, self.collect_settings().shortcuts)
                )
                _set_widget_property(
                    self.status_label, "status", "dirty" if self.dirty else "saved"
                )
        if self.save_button is not None:
            self.save_button.setEnabled(result.ok)
        if self.apply_button is not None:
            self.apply_button.setEnabled(result.ok and self.dirty)
        return result

    def apply(self, *, close: bool = False) -> bool:
        from PySide6 import QtWidgets

        raw_settings = self.collect_settings()
        result = validate_shortcuts(raw_settings.shortcuts)
        if not result.ok:
            self.update_validation()
            return False
        settings = normalise_settings(raw_settings)

        if self.ctx.config_store is not None:
            try:
                self.ctx.config_store.save(settings)
            except Exception as exc:  # noqa: BLE001
                _log.exception("config save failed")
                QtWidgets.QMessageBox.critical(
                    self.window,
                    "Windows Rectangle",
                    f"Could not save preferences:\n{exc}",
                )
                return False

        self.ctx.apply_settings(settings)
        bound = self.ctx.rebind_hotkeys()
        expected = _enabled_shortcut_count(settings.shortcuts)
        if self.ctx.hotkeys is not None and bound < expected:
            QtWidgets.QMessageBox.warning(
                self.window,
                "Windows Rectangle",
                f"Saved, but only {bound} of {expected} shortcuts registered.",
            )
        self.refresh_from_context()
        if close:
            self.window.hide()
        return True


def action_label(action: Action) -> str:
    return _ACTION_LABELS.get(action, action.value.replace("_", " ").title())


def ordered_actions(shortcuts: dict[Action, str] | None = None) -> list[Action]:
    grouped = [action for _, actions in ACTION_GROUPS for action in actions]
    if shortcuts is None:
        return grouped
    present_grouped = [action for action in grouped if action in shortcuts]
    remaining = [action for action in shortcuts if action not in grouped]
    return present_grouped + sorted(remaining, key=lambda a: a.value)


def validate_shortcuts(shortcuts: dict[Action, str]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[str, Action] = {}

    for action in ordered_actions(shortcuts):
        combo = shortcuts.get(action, "")
        if not combo.strip():
            continue
        try:
            parsed = parse(combo)
            translate(parsed)
        except (ShortcutParseError, UnsupportedKeyError) as exc:
            errors.append(f"{action_label(action)}: {exc}")
            continue

        canonical = str(parsed)
        previous = seen.get(canonical)
        if previous is not None:
            errors.append(
                f"{action_label(action)} duplicates {action_label(previous)} ({canonical})"
            )
        else:
            seen[canonical] = action

        if is_reserved(canonical):
            warnings.append(f"{action_label(action)} uses reserved shortcut {canonical}")

    return ValidationResult(tuple(errors), tuple(warnings))


def normalise_settings(settings: Settings) -> Settings:
    shortcuts: dict[Action, str] = {}
    for action, combo in settings.shortcuts.items():
        shortcuts[action] = "" if not combo.strip() else str(parse(combo))
    return Settings(
        shortcuts=shortcuts,
        gap=max(0, int(settings.gap)),
        launch_at_login=bool(settings.launch_at_login),
        cycle_idle_timeout=max(0.1, float(settings.cycle_idle_timeout)),
        drag_to_edge_enabled=bool(settings.drag_to_edge_enabled),
        almost_maximize_scale=max(0.5, min(1.0, float(settings.almost_maximize_scale))),
    )


def show(ctx: AppContext) -> PreferencesController:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    existing = getattr(app, "_windows_rectangle_preferences", None)
    if isinstance(existing, PreferencesController):
        if not existing.dirty:
            existing.refresh_from_context()
        existing.window.show()
        existing.window.raise_()
        existing.window.activateWindow()
        return existing

    controller = _build_window(ctx, QtCore, QtWidgets)
    app._windows_rectangle_preferences = controller
    controller.window.show()
    controller.window.raise_()
    controller.window.activateWindow()
    return controller


def _build_window(ctx: AppContext, QtCore, QtWidgets) -> PreferencesController:
    from PySide6 import QtGui

    class PreferencesDialog(QtWidgets.QDialog):
        controller: PreferencesController | None = None

        def closeEvent(self, event) -> None:
            if self.controller is not None:
                if not _confirm_discard_if_dirty(self.controller, QtWidgets):
                    event.ignore()
                    return
                self.controller.refresh_from_context()
            super().closeEvent(event)

    window = PreferencesDialog()
    window.setObjectName("preferencesWindow")
    window.setWindowTitle("Windows Rectangle")
    window.setMinimumSize(820, 620)
    window.resize(900, 720)
    window.setFont(QtGui.QFont("Segoe UI", 9))
    icon = build_qicon(QtGui)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
    _apply_window_style(window)

    controller = PreferencesController(ctx=ctx, window=window)
    window.controller = controller

    root = QtWidgets.QVBoxLayout(window)
    root.setContentsMargins(20, 18, 20, 16)
    root.setSpacing(14)

    header = QtWidgets.QHBoxLayout()
    title_stack = QtWidgets.QVBoxLayout()
    title_stack.setSpacing(2)
    title = QtWidgets.QLabel("Windows Rectangle")
    title.setObjectName("windowTitle")
    subtitle = QtWidgets.QLabel("Preferences")
    subtitle.setObjectName("windowSubtitle")
    title_stack.addWidget(title)
    title_stack.addWidget(subtitle)
    header.addLayout(title_stack, 1)
    root.addLayout(header)

    tabs = QtWidgets.QTabWidget()
    tabs.setObjectName("preferencesTabs")
    tabs.addTab(_build_shortcuts_tab(controller, QtCore, QtGui, QtWidgets), "Shortcuts")
    tabs.addTab(_build_general_tab(controller, QtWidgets), "General")
    root.addWidget(tabs)

    controller.status_label = QtWidgets.QLabel()
    controller.status_label.setObjectName("statusLabel")
    controller.status_label.setMinimumHeight(22)

    buttons = QtWidgets.QDialogButtonBox()
    reset = buttons.addButton("Restore Defaults", QtWidgets.QDialogButtonBox.ResetRole)
    controller.apply_button = buttons.addButton("Apply", QtWidgets.QDialogButtonBox.ApplyRole)
    controller.save_button = buttons.addButton("Save", QtWidgets.QDialogButtonBox.AcceptRole)
    close = buttons.addButton("Close", QtWidgets.QDialogButtonBox.RejectRole)

    footer = QtWidgets.QHBoxLayout()
    footer.addWidget(controller.status_label, 1)
    footer.addWidget(buttons, 0)
    root.addLayout(footer)

    reset.clicked.connect(lambda: _reset_defaults(controller))
    controller.apply_button.clicked.connect(lambda: controller.apply(close=False))
    controller.save_button.clicked.connect(lambda: controller.apply(close=True))

    def close_without_saving() -> None:
        if _confirm_discard_if_dirty(controller, QtWidgets):
            controller.refresh_from_context()
            window.hide()

    close.clicked.connect(close_without_saving)

    controller.refresh_from_context()
    return controller


def _build_shortcuts_tab(controller: PreferencesController, QtCore, QtGui, QtWidgets):
    tab = QtWidgets.QWidget()
    outer = QtWidgets.QVBoxLayout(tab)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(10)

    search = QtWidgets.QLineEdit()
    search.setObjectName("shortcutSearch")
    search.setAccessibleName("Search commands")
    search.setClearButtonEnabled(True)
    search.setPlaceholderText("Search commands")
    outer.addWidget(search)

    scroll = QtWidgets.QScrollArea()
    scroll.setObjectName("shortcutScroll")
    scroll.setAccessibleName("Shortcut commands")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    content = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    sections = []

    for group_name, actions in ACTION_GROUPS:
        section_label = QtWidgets.QLabel(group_name)
        section_label.setObjectName("sectionHeading")
        section_label.setAccessibleName(f"{group_name} shortcut section")
        layout.addWidget(section_label)
        section_rows = []
        for action in actions:
            row = QtWidgets.QFrame()
            row.setObjectName("shortcutRow")
            row.setProperty("action", action.value)
            row.setProperty("group", group_name)
            row.setAccessibleName(f"{action_label(action)} shortcut row")
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(12, 7, 12, 7)
            row_layout.setSpacing(12)

            label = QtWidgets.QLabel(action_label(action))
            label.setObjectName("commandLabel")
            label.setAccessibleName(action_label(action))
            label.setMinimumWidth(220)

            edit = _build_shortcut_button(controller, action, QtCore, QtGui, QtWidgets)
            controller.shortcut_widgets[action] = edit
            row_layout.addWidget(label, 1)
            row_layout.addWidget(edit, 0)
            layout.addWidget(row)
            section_rows.append((row, action_label(action), group_name))
        sections.append((section_label, section_rows))

    layout.addStretch(1)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    search.textChanged.connect(lambda text: _filter_shortcut_rows(sections, text))
    return tab


def _build_shortcut_button(
    controller: PreferencesController, action: Action, QtCore, QtGui, QtWidgets
):
    action_name = action_label(action)

    class ShortcutButton(QtWidgets.QPushButton):
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("shortcutButton")
            self._sequence = QtGui.QKeySequence()
            self.setCursor(QtCore.Qt.PointingHandCursor)
            self.setMinimumHeight(34)
            self.setMinimumWidth(220)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self.setToolTip("Record Shortcut")
            self.setAccessibleName(f"{action_name} shortcut")
            self.setAutoDefault(False)
            self.setDefault(False)
            self.clicked.connect(lambda _checked=False: self._record())
            self._sync_text()

        def keySequence(self):
            return self._sequence

        def setKeySequence(self, sequence) -> None:
            self._sequence = sequence
            self._sync_text()

        def _record(self) -> None:
            hotkeys_suspended = _suspend_hotkeys_for_recording(controller)
            try:
                sequence = _record_shortcut(self.window(), action_name, QtCore, QtGui, QtWidgets)
            finally:
                if hotkeys_suspended:
                    try:
                        controller.ctx.rebind_hotkeys()
                    except Exception:  # noqa: BLE001
                        _log.exception("could not restore hotkeys after recording shortcut")
            if sequence is None:
                return
            self.setKeySequence(sequence)
            controller.mark_dirty()

        def _sync_text(self) -> None:
            text = self._sequence.toString(QtGui.QKeySequence.PortableText).strip()
            _set_widget_property(self, "shortcutState", "set" if text else "disabled")
            self.setText(_shortcut_button_text(text))

    return ShortcutButton()


def _record_shortcut(parent, action_name: str, QtCore, QtGui, QtWidgets):
    dialog = QtWidgets.QDialog(parent)
    dialog.setObjectName("recordShortcutDialog")
    dialog.setWindowTitle("Record Shortcut")
    dialog.setModal(True)
    dialog.resize(360, 140)
    dialog.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)

    layout = QtWidgets.QVBoxLayout(dialog)
    title = QtWidgets.QLabel("Record Shortcut")
    title.setObjectName("recordShortcutTitle")
    layout.addWidget(title)
    action_label_widget = QtWidgets.QLabel(action_name)
    action_label_widget.setObjectName("recordShortcutAction")
    layout.addWidget(action_label_widget)

    editor = QtWidgets.QKeySequenceEdit(dialog)
    editor.setObjectName("recordShortcutEditor")
    with suppress(AttributeError):
        editor.setMaximumSequenceLength(1)
    editor.clear()
    layout.addWidget(editor)

    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
    clear = buttons.addButton("Clear", QtWidgets.QDialogButtonBox.ResetRole)
    buttons.rejected.connect(dialog.reject)
    clear.clicked.connect(lambda: _clear_recorded_shortcut(dialog, editor))
    layout.addWidget(buttons)

    def accept_recorded_shortcut(sequence) -> None:
        if sequence.toString(QtGui.QKeySequence.PortableText).strip():
            QtCore.QTimer.singleShot(250, dialog.accept)

    editor.keySequenceChanged.connect(accept_recorded_shortcut)
    QtCore.QTimer.singleShot(0, lambda: editor.setFocus(QtCore.Qt.ShortcutFocusReason))

    if dialog.exec() != QtWidgets.QDialog.Accepted:
        return None
    return editor.keySequence()


def _clear_recorded_shortcut(dialog, editor) -> None:
    editor.clear()
    dialog.accept()


def _suspend_hotkeys_for_recording(controller: PreferencesController) -> bool:
    if controller.ctx.hotkeys is None:
        return False
    try:
        controller.ctx.hotkeys.unregister_all()
    except Exception:  # noqa: BLE001
        _log.exception("could not suspend hotkeys while recording shortcut")
        return False
    return True


def _filter_shortcut_rows(sections, query: str) -> None:
    for section_label, rows in sections:
        visible_count = 0
        for row, action_name, group_name in rows:
            visible = _matches_shortcut_filter(action_name, group_name, query)
            row.setVisible(visible)
            visible_count += int(visible)
        section_label.setVisible(visible_count > 0)


def _matches_shortcut_filter(action_name: str, group_name: str, query: str) -> bool:
    terms = query.casefold().split()
    if not terms:
        return True
    haystack = f"{action_name} {group_name}".casefold()
    return all(term in haystack for term in terms)


def _confirm_discard_if_dirty(controller: PreferencesController, QtWidgets) -> bool:
    if not controller.dirty:
        return True
    reply = QtWidgets.QMessageBox.question(
        controller.window,
        "Windows Rectangle",
        "Discard unsaved changes?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No,
    )
    return reply == QtWidgets.QMessageBox.Yes


def _status_text(dirty: bool, shortcuts: dict[Action, str]) -> str:
    enabled_count = _enabled_shortcut_count(shortcuts)
    prefix = "Unsaved changes" if dirty else "Saved"
    suffix = "shortcut" if enabled_count == 1 else "shortcuts"
    return f"{prefix} - {enabled_count} {suffix} enabled"


def _set_widget_property(widget, name: str, value: object) -> None:
    with suppress(AttributeError):
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _apply_window_style(window) -> None:
    window.setStyleSheet(
        """
        QDialog#preferencesWindow {
            background: #f6f7f9;
            color: #20242a;
            font-family: "Segoe UI";
            font-size: 13px;
        }
        QLabel#windowTitle {
            color: #171a1f;
            font-size: 20px;
            font-weight: 600;
        }
        QLabel#windowSubtitle {
            color: #667085;
        }
        QTabWidget#preferencesTabs::pane {
            background: #ffffff;
            border: 1px solid #d9dee7;
            border-radius: 6px;
            top: -1px;
        }
        QTabWidget#preferencesTabs QTabBar::tab {
            background: transparent;
            border: 1px solid transparent;
            color: #475467;
            padding: 8px 16px;
            margin-right: 2px;
        }
        QTabWidget#preferencesTabs QTabBar::tab:selected {
            background: #ffffff;
            border-color: #d9dee7;
            border-bottom-color: #ffffff;
            color: #182230;
            font-weight: 600;
        }
        QLineEdit#shortcutSearch {
            background: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
            min-height: 34px;
            padding: 0 10px;
        }
        QLineEdit#shortcutSearch:focus {
            border-color: #2f6fed;
        }
        QScrollArea#shortcutScroll {
            background: #ffffff;
        }
        QLabel#sectionHeading {
            color: #344054;
            font-weight: 600;
            padding: 16px 12px 7px 12px;
        }
        QFrame#shortcutRow {
            background: #ffffff;
            border-bottom: 1px solid #eef1f5;
        }
        QLabel#commandLabel {
            color: #20242a;
            font-weight: 500;
        }
        QPushButton#shortcutButton {
            background: #f8fafc;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
            color: #182230;
            padding: 6px 12px;
            text-align: center;
        }
        QPushButton#shortcutButton:hover {
            background: #eef4ff;
            border-color: #84adff;
        }
        QPushButton#shortcutButton:focus {
            border-color: #2f6fed;
        }
        QPushButton#shortcutButton[shortcutState="disabled"] {
            color: #667085;
            background: #f2f4f7;
            border-style: dashed;
        }
        QDialog#recordShortcutDialog {
            background: #ffffff;
        }
        QLabel#recordShortcutTitle {
            color: #171a1f;
            font-size: 17px;
            font-weight: 600;
        }
        QLabel#recordShortcutAction {
            color: #475467;
            padding-bottom: 4px;
        }
        QKeySequenceEdit#recordShortcutEditor {
            background: #ffffff;
            border: 1px solid #2f6fed;
            border-radius: 6px;
            min-height: 36px;
            padding: 0 10px;
        }
        QLabel#statusLabel {
            color: #475467;
            padding: 5px 0;
        }
        QLabel#statusLabel[status="saved"] {
            color: #1f6f43;
        }
        QLabel#statusLabel[status="dirty"] {
            color: #8a5a00;
        }
        QLabel#statusLabel[status="warning"] {
            color: #8a5a00;
        }
        QLabel#statusLabel[status="error"] {
            color: #b42318;
        }
        QDialogButtonBox QPushButton {
            min-height: 30px;
            min-width: 86px;
            padding: 4px 12px;
        }
        QSpinBox, QDoubleSpinBox {
            background: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 6px;
            padding: 0 8px;
        }
        QCheckBox {
            min-height: 30px;
        }
        """
    )


def _build_general_tab(controller: PreferencesController, QtWidgets):
    widget = QtWidgets.QWidget()
    widget.setObjectName("generalTab")
    form = QtWidgets.QFormLayout(widget)
    form.setContentsMargins(12, 12, 12, 12)
    form.setHorizontalSpacing(24)
    form.setVerticalSpacing(14)
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

    controller.gap_spin = QtWidgets.QSpinBox()
    controller.gap_spin.setRange(0, 200)
    controller.gap_spin.setSuffix(" px")
    controller.gap_spin.setMinimumHeight(32)
    controller.gap_spin.valueChanged.connect(lambda _value: controller.mark_dirty())
    form.addRow("Gap", controller.gap_spin)

    controller.cycle_spin = QtWidgets.QDoubleSpinBox()
    controller.cycle_spin.setRange(0.1, 10.0)
    controller.cycle_spin.setSingleStep(0.1)
    controller.cycle_spin.setDecimals(1)
    controller.cycle_spin.setSuffix(" s")
    controller.cycle_spin.setMinimumHeight(32)
    controller.cycle_spin.valueChanged.connect(lambda _value: controller.mark_dirty())
    form.addRow("Cycle timeout", controller.cycle_spin)

    controller.almost_spin = QtWidgets.QSpinBox()
    controller.almost_spin.setRange(50, 100)
    controller.almost_spin.setSuffix(" %")
    controller.almost_spin.setMinimumHeight(32)
    controller.almost_spin.valueChanged.connect(lambda _value: controller.mark_dirty())
    form.addRow("Middle majority", controller.almost_spin)

    controller.drag_checkbox = QtWidgets.QCheckBox("Drag to edge snapping")
    controller.drag_checkbox.toggled.connect(lambda _checked: controller.mark_dirty())
    form.addRow("", controller.drag_checkbox)

    controller.launch_checkbox = QtWidgets.QCheckBox("Launch at login")
    controller.launch_checkbox.toggled.connect(lambda _checked: controller.mark_dirty())
    form.addRow("", controller.launch_checkbox)

    return widget


def _load_settings_into_widgets(controller: PreferencesController, settings: Settings) -> None:
    from PySide6 import QtGui

    for action, edit in controller.shortcut_widgets.items():
        combo = settings.shortcuts.get(action, DEFAULT_SHORTCUTS.get(action, ""))
        edit.setKeySequence(QtGui.QKeySequence(_qt_sequence_text(combo)))

    if controller.gap_spin is not None:
        controller.gap_spin.setValue(int(settings.gap))
    if controller.cycle_spin is not None:
        controller.cycle_spin.setValue(float(settings.cycle_idle_timeout))
    if controller.almost_spin is not None:
        controller.almost_spin.setValue(int(round(float(settings.almost_maximize_scale) * 100)))
    if controller.drag_checkbox is not None:
        controller.drag_checkbox.setChecked(bool(settings.drag_to_edge_enabled))
    if controller.launch_checkbox is not None:
        controller.launch_checkbox.setChecked(bool(settings.launch_at_login))


def _reset_defaults(controller: PreferencesController) -> None:
    from PySide6 import QtGui

    for action, combo in DEFAULT_SHORTCUTS.items():
        widget = controller.shortcut_widgets.get(action)
        if widget is not None:
            widget.setKeySequence(QtGui.QKeySequence(_qt_sequence_text(combo)))
    controller.mark_dirty()


def _sequence_text(widget) -> str:
    from PySide6 import QtGui

    return widget.keySequence().toString(QtGui.QKeySequence.PortableText).strip()


def _enabled_shortcut_count(shortcuts: dict[Action, str]) -> int:
    return sum(1 for combo in shortcuts.values() if combo.strip())


def _shortcut_button_text(combo: str) -> str:
    if not combo.strip():
        return "Disabled"
    try:
        parsed = parse(combo)
    except ShortcutParseError:
        return combo.strip()
    parts = [_DISPLAY_MODIFIERS[m] for m in parsed.modifiers]
    key = _DISPLAY_KEYS.get(parsed.key)
    if key is None:
        key = parsed.key.upper() if len(parsed.key) == 1 and parsed.key.isalpha() else parsed.key
    parts.append(key)
    return "+".join(parts)


def _qt_sequence_text(combo: str) -> str:
    if not combo.strip():
        return ""
    parsed = parse(combo)
    parts = [_QT_MODIFIERS[m] for m in parsed.modifiers]
    key = _QT_KEYS.get(parsed.key)
    if key is None:
        key = parsed.key.upper() if len(parsed.key) == 1 and parsed.key.isalpha() else parsed.key
    parts.append(key)
    return "+".join(parts)
