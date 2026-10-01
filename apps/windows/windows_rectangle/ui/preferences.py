"""Preferences staging + launcher (brief §2 #15).

Two layers in this module:

1. `PrefsController` — pure-Python staging service. Owns the working
   copy of Settings, applies validation, exposes `set_*`/`commit`/
   `revert`. Fully unit-testable without PySide6.

2. `open_prefs_window(ctx, dialog_factory)` — the integration point
   between the tray menu and a Qt QDialog. Builds a PrefsController
   from the AppContext, hands it to the supplied `dialog_factory` (a
   callable returning an object with `.exec() -> bool`), and on
   acceptance commits via `ctx.config_store.save` + `ctx.apply_settings`.

Splitting these means we can unit-test every interaction the prefs UI
cares about — staging a gap change, rebinding a shortcut, seeing a
duplicate-binding warning — without spinning up Qt; and we can pass a
fake dialog factory in tests to verify the commit-vs-cancel paths.

`commit` does NOT touch the OS itself — the caller wires the save/apply
callbacks. This keeps the controller importable without any adapters.
"""

from __future__ import annotations

import copy
import html
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field

from ..core.actions import DEFAULT_SHORTCUTS, Action
from ..core.shortcuts import (
    ShortcutParseError,
    is_reserved,
)
from ..core.shortcuts import (
    conflicts as shortcut_conflicts,
)
from ..core.shortcuts import (
    normalise as normalise_combo,
)
from ..ports.config_store import Settings

# Gap is a single int in physical pixels. Negative gaps make no sense;
# very large gaps just look silly — clamp at 256 (≈¼ of a 1080p height).
GAP_MIN = 0
GAP_MAX = 256

# almost_maximize_scale lives in (0, 1]. 0.85 is the brief default.
ALMOST_MAX_MIN = 0.1
ALMOST_MAX_MAX = 1.0

# cycle_idle_timeout in seconds: 0 disables cycling (every press is a
# fresh dispatch), small values feel snappy, large values surprise users.
CYCLE_TIMEOUT_MIN = 0.0
CYCLE_TIMEOUT_MAX = 10.0


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Result of `PrefsController.validate()`.

    `errors` are blocking — the UI must prevent commit.
    `warnings` are advisory — the UI shows them but allows commit (e.g.
    "this combo clashes with Windows Snap").
    """

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class PrefsController:
    """Staged-edits service over a Settings dataclass.

    Holds two copies: the `baseline` (the committed-on-disk snapshot)
    and `staged` (the user's in-flight edits). `is_dirty` compares them.
    """

    baseline: Settings
    staged: Settings = field(init=False)

    def __post_init__(self) -> None:
        # Snapshot baseline too — otherwise it aliases the caller's
        # Settings instance, and any later external mutation of that
        # object (e.g. ctx.apply_settings firing while prefs is open)
        # would silently change what `is_dirty` compares against.
        self.baseline = self._snapshot(self.baseline)
        self.staged = self._snapshot(self.baseline)

    # ----- staging mutators -------------------------------------------

    def set_gap(self, gap: int) -> None:
        if not isinstance(gap, int) or isinstance(gap, bool):
            raise TypeError("gap must be int")
        self.staged.gap = max(GAP_MIN, min(GAP_MAX, gap))

    def set_launch_at_login(self, enabled: bool) -> None:
        self.staged.launch_at_login = bool(enabled)

    def set_drag_to_edge_enabled(self, enabled: bool) -> None:
        self.staged.drag_to_edge_enabled = bool(enabled)

    def set_almost_maximize_scale(self, scale: float) -> None:
        # Clamp instead of raise — the UI slider can land just outside.
        self.staged.almost_maximize_scale = max(ALMOST_MAX_MIN, min(ALMOST_MAX_MAX, float(scale)))

    def set_cycle_idle_timeout(self, seconds: float) -> None:
        self.staged.cycle_idle_timeout = max(
            CYCLE_TIMEOUT_MIN, min(CYCLE_TIMEOUT_MAX, float(seconds))
        )

    def set_shortcut(self, action: Action, combo: str) -> None:
        """Stage a shortcut rebind. Raises `ShortcutParseError` if the
        combo is unparseable — UI calls this from a try/except to show
        an inline error without committing.
        """
        # Parse for side-effect (validation); we store the *normalised* form
        # so duplicate detection later doesn't depend on whitespace/case.
        canonical = normalise_combo(combo)
        self.staged.shortcuts[action] = canonical

    def clear_shortcut(self, action: Action) -> None:
        """Remove a shortcut binding. Cleared shortcuts won't register."""
        self.staged.shortcuts.pop(action, None)

    # ----- inspection -------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self.staged != self.baseline

    def shortcut_conflicts(self) -> dict[Action, list[Action]]:
        """Group actions whose canonical combo collides with another.

        Maps `winner_action -> [other_action, ...]` — the first action
        wins the slot, the rest are flagged duplicates. Used by the UI
        to render red strikethroughs in the table.
        """
        # `core.shortcuts.conflicts` works on a {name: combo} mapping;
        # we adapt our Action keys to/from strings for that call.
        as_strings = {a.value: c for a, c in self.staged.shortcuts.items()}
        raw = shortcut_conflicts(as_strings)
        out: dict[Action, list[Action]] = {}
        for winner_str, dupes in raw.items():
            winner = Action(winner_str)
            out[winner] = [Action(d) for d in dupes]
        return out

    def reserved_bindings(self) -> list[tuple[Action, str]]:
        """List staged shortcuts that step on an OS-reserved combo."""
        return [
            (action, combo) for action, combo in self.staged.shortcuts.items() if is_reserved(combo)
        ]

    def validate(self) -> ValidationReport:
        """Compute a fresh report against the current `staged` state."""
        errors: list[str] = []
        warnings: list[str] = []

        # Range sanity (clamped on set, but a direct .staged mutation
        # could bypass — guard anyway).
        if not (GAP_MIN <= self.staged.gap <= GAP_MAX):
            errors.append(f"gap {self.staged.gap} out of range [{GAP_MIN}, {GAP_MAX}]")
        if not (ALMOST_MAX_MIN <= self.staged.almost_maximize_scale <= ALMOST_MAX_MAX):
            errors.append(
                f"almost_maximize_scale {self.staged.almost_maximize_scale} "
                f"out of range [{ALMOST_MAX_MIN}, {ALMOST_MAX_MAX}]"
            )
        if not (CYCLE_TIMEOUT_MIN <= self.staged.cycle_idle_timeout <= CYCLE_TIMEOUT_MAX):
            errors.append(
                f"cycle_idle_timeout {self.staged.cycle_idle_timeout} "
                f"out of range [{CYCLE_TIMEOUT_MIN}, {CYCLE_TIMEOUT_MAX}]"
            )

        # Shortcut sanity — parse failures become errors, conflicts/reserved
        # become warnings (the user might want to keep a power-user combo).
        for action, combo in self.staged.shortcuts.items():
            try:
                normalise_combo(combo)
            except ShortcutParseError as e:
                errors.append(f"{action.value}: cannot parse {combo!r}: {e}")

        dupes = self.shortcut_conflicts()
        for winner, others in dupes.items():
            for other in others:
                warnings.append(
                    f"{other.value} shares combo with {winner.value} — only one will fire"
                )

        for action, combo in self.reserved_bindings():
            warnings.append(f"{action.value}: {combo} clashes with an OS-reserved shortcut")

        return ValidationReport(tuple(errors), tuple(warnings))

    # ----- commit / revert --------------------------------------------

    def commit(
        self,
        on_save: Callable[[Settings], None] | None = None,
        on_apply: Callable[[Settings], None] | None = None,
        *,
        current_settings: Settings | None = None,
    ) -> ValidationReport:
        """Validate and, if clean, persist + apply the staged settings.

        - `on_save(settings)` typically wraps `ConfigStore.save`.
        - `on_apply(settings)` typically wraps `AppContext.apply_settings`.

        Returns the ValidationReport. If `report.ok` is False, neither
        callback fires and the baseline is untouched.
        """
        report = self.validate()
        if not report.ok:
            return report
        candidate = (
            self._snapshot(current_settings) if current_settings is not None else self.staged
        )
        if current_settings is not None:
            for name in (
                "gap",
                "launch_at_login",
                "cycle_idle_timeout",
                "drag_to_edge_enabled",
                "almost_maximize_scale",
            ):
                if getattr(self.staged, name) != getattr(self.baseline, name):
                    setattr(candidate, name, getattr(self.staged, name))
            for action in self.baseline.shortcuts.keys() | self.staged.shortcuts.keys():
                if self.staged.shortcuts.get(action) != self.baseline.shortcuts.get(action):
                    if action in self.staged.shortcuts:
                        candidate.shortcuts[action] = self.staged.shortcuts[action]
                    else:
                        candidate.shortcuts.pop(action, None)
            report = PrefsController(candidate).validate()
            if not report.ok:
                return report
        if on_save is not None:
            on_save(candidate)
        if on_apply is not None:
            on_apply(candidate)
        # Promote staged → baseline; copy so further edits don't mutate
        # what we just handed to the callbacks.
        self.baseline = self._snapshot(candidate)
        self.staged = self._snapshot(self.baseline)
        return report

    def revert(self) -> None:
        """Throw away staged changes and start fresh from baseline."""
        self.staged = self._snapshot(self.baseline)

    def reset_shortcuts_to_defaults(self) -> None:
        """Replace staged shortcuts with `DEFAULT_SHORTCUTS`.

        Useful for the dialog's "Reset shortcuts" button: a user who's
        rebound several actions and now wants the default Rectangle
        defaults back doesn't have to retype each combo.

        Leaves non-shortcut fields (gap, drag-to-edge, etc.) untouched —
        users typically want to keep their gap setting even when
        nuking shortcut customisations.
        """
        # Import here so the controller module stays Settings-only at
        # module-load time (matches the lazy-Qt pattern elsewhere).
        from ..core.actions import DEFAULT_SHORTCUTS

        # Copy DEFAULT_SHORTCUTS so the user's subsequent edits don't
        # pollute the module-level constant.
        self.staged.shortcuts = dict(DEFAULT_SHORTCUTS)

    # ----- internals --------------------------------------------------

    @staticmethod
    def _snapshot(settings: Settings) -> Settings:
        """Deep-copy Settings so mutable fields (`shortcuts` dict) are
        independent between staged and baseline."""
        return copy.deepcopy(settings)


# ----- launcher ----------------------------------------------------------


# A `DialogFactory` takes the PrefsController and returns an object whose
# `.exec()` returns True on accept, False on cancel. Real Qt dialogs
# match this contract; tests can pass a fake.
class _DialogProtocol:
    def exec(self) -> bool: ...  # pragma: no cover — typing only


DialogFactory = Callable[["PrefsController"], _DialogProtocol]


def open_prefs_window(
    ctx: AppContextLike,
    *,
    dialog_factory: DialogFactory,
) -> ValidationReport | None:
    """Open the preferences dialog and, on accept, commit through `ctx`.

    Builds a fresh `PrefsController` from `ctx.settings` (so the user
    edits a snapshot, not the live `ctx`), hands it to `dialog_factory`,
    and runs the dialog modally. If the user clicks OK, commits via the
    ctx's `config_store.save` (if present) and `apply_settings`.

    Returns the ValidationReport if a commit happened, or None if the
    user cancelled. Callers can inspect the report for warnings.
    """
    pc = PrefsController(baseline=ctx.settings)
    dlg = dialog_factory(pc)
    if not dlg.exec():
        return None
    on_save = ctx.config_store.save if ctx.config_store is not None else None
    return pc.commit(on_save=on_save, on_apply=ctx.apply_settings, current_settings=ctx.settings)


# Structural alias for AppContext — we only touch four attributes, so
# we can stay decoupled from the heavyweight app module.
class AppContextLike:  # pragma: no cover — typing only
    settings: Settings
    config_store: object | None

    def apply_settings(self, settings: Settings) -> None: ...


# ----- modeless Qt preferences window ---------------------------------


def ordered_actions() -> list[Action]:
    return list(Action)


def action_label(action: Action) -> str:
    from .cheat_sheet import ACTION_LABELS

    return ACTION_LABELS[action].title()


def _sequence_text(button) -> str:
    from PySide6 import QtGui

    return button.keySequence().toString(QtGui.QKeySequence.PortableText)


def _qt_sequence_text(combo: str) -> str:
    if not combo:
        return ""
    try:
        combo = normalise_combo(combo)
    except ShortcutParseError:
        return combo  # Keep malformed stored bindings visible to validation.
    return combo.replace("win+", "Meta+").replace("pageup", "PgUp").replace("pagedown", "PgDown")


def _canonical_sequence_text(text: str) -> str:
    return normalise_combo(text.replace("PgUp", "PageUp").replace("PgDown", "PageDown"))


def _record_shortcut(parent, action_name: str, qt_core, qt_gui, qt_widgets):
    dialog = qt_widgets.QDialog(parent)
    dialog.setObjectName("recordShortcutDialog")
    dialog.setWindowTitle(f"Record Shortcut — {action_name}")
    layout = qt_widgets.QVBoxLayout(dialog)
    layout.addWidget(qt_widgets.QLabel("Press the shortcut you want to use."))
    editor = qt_widgets.QKeySequenceEdit(dialog)
    editor.setObjectName("recordShortcutEditor")
    editor.setAccessibleName(f"Record {action_name} shortcut")
    layout.addWidget(editor)
    buttons = qt_widgets.QDialogButtonBox(
        qt_widgets.QDialogButtonBox.Ok | qt_widgets.QDialogButtonBox.Cancel
    )
    clear = buttons.addButton("Clear", qt_widgets.QDialogButtonBox.ActionRole)
    clear.clicked.connect(lambda: (editor.clear(), dialog.accept()))
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    editor.setFocus()
    return editor.keySequence() if dialog.exec() == qt_widgets.QDialog.Accepted else None


class PreferencesController:
    def __init__(
        self,
        ctx,
        window,
        shortcut_widgets,
        rows,
        sections,
        status_label,
        binding_status_label,
        save_button,
        apply_button,
        retry_button,
        gap_spin,
        cycle_spin,
        almost_spin,
        drag_checkbox,
        launch_checkbox,
    ):
        self.ctx = ctx
        self.window = window
        self.shortcut_widgets = shortcut_widgets
        self.rows = rows
        self.sections = sections
        self.status_label = status_label
        self.binding_status_label = binding_status_label
        self.save_button = save_button
        self.apply_button = apply_button
        self.retry_button = retry_button
        self.gap_spin = gap_spin
        self.cycle_spin = cycle_spin
        self.almost_spin = almost_spin
        self.drag_checkbox = drag_checkbox
        self.launch_checkbox = launch_checkbox
        self.dirty = False

    def load_settings(self, settings: Settings) -> None:
        from PySide6 import QtGui

        self._baseline = copy.deepcopy(settings)
        controls = (
            self.gap_spin,
            self.cycle_spin,
            self.almost_spin,
            self.drag_checkbox,
            self.launch_checkbox,
        )
        for control in controls:
            control.blockSignals(True)
        self.gap_spin.setValue(settings.gap)
        self.cycle_spin.setValue(settings.cycle_idle_timeout)
        self.almost_spin.setValue(round(settings.almost_maximize_scale * 100))
        self.drag_checkbox.setChecked(settings.drag_to_edge_enabled)
        self.launch_checkbox.setChecked(settings.launch_at_login)
        for control in controls:
            control.blockSignals(False)
        self._baseline_cycle_value = self.cycle_spin.value()
        for action, button in self.shortcut_widgets.items():
            combo = _qt_sequence_text(settings.shortcuts.get(action, ""))
            button.setKeySequence(QtGui.QKeySequence(combo))
        self._baseline_sequences = {
            action: _sequence_text(button) for action, button in self.shortcut_widgets.items()
        }
        self.dirty = False
        self._refresh_status()

    def collect_settings(self) -> Settings:
        settings = copy.deepcopy(self.ctx.settings)
        values = {
            "gap": self.gap_spin.value(),
            "cycle_idle_timeout": self.cycle_spin.value(),
            "almost_maximize_scale": self.almost_spin.value() / 100,
            "drag_to_edge_enabled": self.drag_checkbox.isChecked(),
            "launch_at_login": self.launch_checkbox.isChecked(),
        }
        for name, value in values.items():
            baseline = getattr(self._baseline, name)
            if name == "almost_maximize_scale":
                baseline = round(baseline * 100) / 100
            elif name == "cycle_idle_timeout":
                baseline = self._baseline_cycle_value
            if value != baseline:
                setattr(settings, name, value)
        for action, button in self.shortcut_widgets.items():
            text = _sequence_text(button)
            if text != self._baseline_sequences[action]:
                combo = _canonical_sequence_text(text) if text else ""
                if combo:
                    settings.shortcuts[action] = combo
                else:
                    settings.shortcuts.pop(action, None)
        return settings

    def _validation(self):
        try:
            candidate = self.collect_settings()
        except ShortcutParseError as exc:
            return None, f"Invalid shortcut: {exc}", "error"
        duplicate = shortcut_conflicts(
            {action.value: combo for action, combo in candidate.shortcuts.items()}
        )
        if duplicate:
            return None, "Shortcut duplicates: only one command can use each combo", "error"
        report = PrefsController(candidate).validate()
        if report.errors:
            return None, report.errors[0], "error"
        if report.warnings:
            return candidate, report.warnings[0], "warning"
        return (
            candidate,
            "Unsaved changes" if self.dirty else "All changes saved",
            "dirty" if self.dirty else "saved",
        )

    def _refresh_status(self) -> None:
        _candidate, message, state = self._validation()
        self.status_label.setText(message)
        self.status_label.setProperty("status", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.save_button.setEnabled(state != "error" and self.dirty)
        self.apply_button.setEnabled(state != "error" and self.dirty)
        self._refresh_binding_status()

    def _refresh_binding_status(self) -> None:
        report = getattr(self.ctx, "last_binding_report", None)
        if report is None or not report.failed_count:
            self.binding_status_label.hide()
            self.retry_button.hide()
            return
        details = [
            f"{action_label(action)} ({combo}): "
            f"{error.strip().splitlines()[0] if error.strip() else 'Registration failed'}"
            for action, combo, error in report.failed
        ]
        details.extend(
            f"{name} ({combo}): "
            f"{error.strip().splitlines()[0] if error.strip() else 'Registration failed'}"
            for _workspace_id, name, combo, error in report.workspace_failed
        )
        count = report.failed_count
        paused = getattr(self.ctx, "paused", False) or report.paused
        summary = (
            f"{'Shortcuts paused. ' if paused else ''}"
            f"Saved settings: {count} shortcut{'s' if count != 1 else ''} unavailable."
        )
        visible = details[:2]
        if count > 2:
            visible.append(f"{count - 2} more; see Binding status in the tray.")
        full_text = "\n".join((summary, *details))
        tooltip_text = html.escape(full_text).replace("\n", "<br>")
        self.binding_status_label.setText("\n".join((summary, *visible)))
        self.binding_status_label.setToolTip(f"<div>{tooltip_text}</div>")
        self.binding_status_label.setAccessibleDescription(full_text)
        self.binding_status_label.show()
        self.retry_button.setEnabled(not paused)
        self.retry_button.setToolTip(
            "Resume shortcuts before retrying" if paused else "Retry registering saved shortcuts"
        )
        self.retry_button.show()

    def retry_shortcuts(self) -> None:
        report = getattr(self.ctx, "last_binding_report", None)
        if (
            report is None
            or not report.failed_count
            or report.paused
            or getattr(self.ctx, "paused", False)
        ):
            return
        try:
            self.ctx.rebind_hotkeys()
        except Exception as exc:  # noqa: BLE001 — keep the failed binding visible
            self._refresh_binding_status()
            self.binding_status_label.setText(
                f"{self.binding_status_label.text()}\nRetry failed: {exc}"
            )
            return
        self._refresh_binding_status()

    def mark_dirty(self) -> None:
        self.dirty = any(
            (
                self.gap_spin.value() != self._baseline.gap,
                self.cycle_spin.value() != self._baseline_cycle_value,
                self.almost_spin.value() != round(self._baseline.almost_maximize_scale * 100),
                self.drag_checkbox.isChecked() != self._baseline.drag_to_edge_enabled,
                self.launch_checkbox.isChecked() != self._baseline.launch_at_login,
            )
        )
        if not self.dirty:
            self.dirty = any(
                _sequence_text(button) != self._baseline_sequences[action]
                for action, button in self.shortcut_widgets.items()
            )
        self._refresh_status()

    def record_action(self, action: Action) -> None:
        from PySide6 import QtCore, QtGui, QtWidgets

        hotkeys = getattr(self.ctx, "hotkeys", None)
        if hotkeys is not None:
            hotkeys.unregister_all()
        try:
            sequence = _record_shortcut(self.window, action_label(action), QtCore, QtGui, QtWidgets)
        finally:
            if hotkeys is not None:
                self.ctx.rebind_hotkeys()
        self._refresh_binding_status()
        if sequence is not None:
            self.shortcut_widgets[action].setKeySequence(sequence)
            self.mark_dirty()

    def save(self, *, close: bool) -> None:
        candidate, _message, state = self._validation()
        if state == "error" or candidate is None or not self.dirty:
            return
        try:
            if self.ctx.config_store is not None:
                self.ctx.config_store.save(candidate)
            binding_report = getattr(self.ctx, "last_binding_report", None)
            retry_failed_bindings = (
                candidate.shortcuts == self.ctx.settings.shortcuts
                and getattr(binding_report, "failed_count", 0) > 0
                and not getattr(self.ctx, "paused", False)
                and not getattr(binding_report, "paused", False)
            )
            self.ctx.apply_settings(candidate)
            if retry_failed_bindings:
                self.ctx.rebind_hotkeys()
        except Exception as exc:  # noqa: BLE001 — surface save failures without losing edits
            self.status_label.setText(f"Could not save preferences: {exc}")
            self.status_label.setProperty("status", "error")
            return
        self.load_settings(self.ctx.settings)
        if close and not getattr(getattr(self.ctx, "last_binding_report", None), "failed_count", 0):
            self.window.hide()


def show(ctx) -> PreferencesController:
    from PySide6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    existing = getattr(app, "_windows_rectangle_preferences", None)
    if isinstance(existing, PreferencesController):
        if not existing.dirty:
            existing.load_settings(ctx.settings)
        else:
            existing._refresh_binding_status()
        existing.window.show()
        existing.window.raise_()
        existing.window.activateWindow()
        return existing
    controller = _build_window(ctx, QtCore, QtWidgets)
    app._windows_rectangle_preferences = controller
    controller.window.show()
    return controller


def _build_window(ctx, qt_core, qt_widgets) -> PreferencesController:
    from PySide6 import QtGui

    from .logo import build_logo_pixmap, build_qicon

    class ShortcutButton(qt_widgets.QPushButton):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._sequence = QtGui.QKeySequence()

        def keySequence(self):
            return self._sequence

        def setKeySequence(self, sequence):
            self._sequence = sequence
            self.setText(sequence.toString(QtGui.QKeySequence.PortableText) or "Unassigned")

    window = qt_widgets.QDialog()
    window.setObjectName("preferencesWindow")
    window.setWindowTitle("Windows Rectangle")
    window.setWindowIcon(build_qicon(QtGui))
    window.setMinimumSize(400, 280)
    available = qt_widgets.QApplication.primaryScreen().availableGeometry()
    window.resize(min(920, available.width() - 32), min(700, available.height() - 48))
    window.setFont(QtGui.QFont("Segoe UI", 10))
    root = qt_widgets.QVBoxLayout(window)
    compact = available.width() < 640 or available.height() < 480
    root.setContentsMargins(*(12, 8, 12, 8) if compact else (22, 18, 22, 18))
    root.setSpacing(6 if compact else 14)
    content_layout = root
    if compact:
        content_scroll = qt_widgets.QScrollArea()
        content_scroll.setObjectName("preferencesContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(qt_widgets.QFrame.NoFrame)
        content = qt_widgets.QWidget()
        content_layout = qt_widgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_scroll.setWidget(content)
        root.addWidget(content_scroll, 1)

    header = qt_widgets.QHBoxLayout()
    brand = qt_widgets.QFrame()
    brand.setObjectName("brandLogoPanel")
    brand.setAccessibleName("Application logo")
    brand.setMinimumSize(196, 56)
    brand_layout = qt_widgets.QHBoxLayout(brand)
    logo = qt_widgets.QLabel()
    logo.setObjectName("brandLogo")
    logo.setAccessibleName("Application logo image")
    logo.setPixmap(build_logo_pixmap(QtGui))
    brand_layout.addWidget(logo)
    header.addWidget(brand)
    heading = qt_widgets.QLabel("Windows Rectangle")
    heading.setObjectName("preferencesHeading")
    header.addWidget(heading, 1)
    content_layout.addLayout(header)

    tabs = qt_widgets.QTabWidget()
    tabs.setObjectName("preferencesTabs")
    if compact:
        tabs.setMaximumHeight(200)
    content_layout.addWidget(tabs, 1)
    shortcuts_page = qt_widgets.QWidget()
    shortcut_layout = qt_widgets.QVBoxLayout(shortcuts_page)
    search = qt_widgets.QLineEdit()
    search.setObjectName("shortcutSearch")
    search.setPlaceholderText("Search commands")
    search.setAccessibleName("Search commands")
    search.setClearButtonEnabled(True)
    shortcut_layout.addWidget(search)

    def focus_search() -> None:
        tabs.setCurrentIndex(0)
        search.setFocus()

    find_shortcut = QtGui.QShortcut(QtGui.QKeySequence.Find, window)
    find_shortcut.activated.connect(focus_search)
    clear_search_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Escape"), search)
    clear_search_shortcut.setContext(qt_core.Qt.WidgetShortcut)
    clear_search_shortcut.activated.connect(search.clear)
    scroll = qt_widgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(qt_widgets.QFrame.NoFrame)
    content = qt_widgets.QWidget()
    rows_layout = qt_widgets.QVBoxLayout(content)
    rows_layout.setSpacing(5)
    sections: dict[str, tuple[object, list[Action]]] = {}
    rows: dict[Action, object] = {}
    shortcut_widgets: dict[Action, object] = {}

    def section_for(action: Action) -> str:
        name = action.value
        if "sixth" in name:
            return "Sixths"
        if "half" in name:
            return "Halves"
        if "quarter" in name or "fourth" in name:
            return "Quarters"
        if "third" in name:
            return "Thirds"
        if "display" in name:
            return "Displays"
        return "Other commands"

    groups: dict[str, list[Action]] = {}
    for action in ordered_actions():
        groups.setdefault(section_for(action), []).append(action)
    for section_name, actions in groups.items():
        label = qt_widgets.QLabel(section_name)
        label.setObjectName("sectionHeading")
        rows_layout.addWidget(label)
        sections[section_name] = (label, actions)
        for action in actions:
            row = qt_widgets.QFrame()
            row.setObjectName("shortcutRow")
            row.setProperty("action", action.value)
            row_layout = qt_widgets.QHBoxLayout(row)
            row_layout.setContentsMargins(10, 3, 10, 3)
            row_layout.addWidget(qt_widgets.QLabel(action_label(action)), 1)
            button = ShortcutButton()
            button.setObjectName("shortcutButton")
            button.setToolTip("Record Shortcut")
            button.setAccessibleName(f"{action_label(action)} shortcut")
            button.setMinimumSize(220, 34)
            row_layout.addWidget(button)
            rows_layout.addWidget(row)
            rows[action] = row
            shortcut_widgets[action] = button
    no_results = qt_widgets.QLabel("No commands found. Try another search.")
    no_results.setObjectName("noShortcutsFound")
    no_results.setAccessibleName("No matching shortcuts")
    no_results.hide()
    rows_layout.addWidget(no_results)
    rows_layout.addStretch(1)
    scroll.setWidget(content)
    shortcut_layout.addWidget(scroll, 1)
    tabs.addTab(shortcuts_page, "Shortcuts")

    general_page = qt_widgets.QWidget()
    general_layout = qt_widgets.QFormLayout(general_page)
    if compact:
        general_layout.setRowWrapPolicy(qt_widgets.QFormLayout.WrapAllRows)
    gap_spin = qt_widgets.QSpinBox()
    gap_spin.setRange(GAP_MIN, GAP_MAX)
    gap_spin.setSuffix(" px")
    cycle_spin = qt_widgets.QDoubleSpinBox()
    cycle_spin.setRange(CYCLE_TIMEOUT_MIN, CYCLE_TIMEOUT_MAX)
    cycle_spin.setSingleStep(0.1)
    cycle_spin.setSuffix(" s")
    almost_spin = qt_widgets.QSpinBox()
    almost_spin.setRange(10, 100)
    almost_spin.setSuffix(" %")
    drag_checkbox = qt_widgets.QCheckBox("Snap windows when dragged to screen edges")
    launch_checkbox = qt_widgets.QCheckBox("Launch at login")
    general_layout.addRow("Gap between windows", gap_spin)
    general_layout.addRow("Repeat-key cycle timeout", cycle_spin)
    general_layout.addRow("Almost-maximize size", almost_spin)
    general_layout.addRow(drag_checkbox)
    general_layout.addRow(launch_checkbox)
    general_scroll = qt_widgets.QScrollArea()
    general_scroll.setObjectName("generalScroll")
    general_scroll.setWidgetResizable(True)
    general_scroll.setFrameShape(qt_widgets.QFrame.NoFrame)
    general_scroll.setWidget(general_page)
    tabs.addTab(general_scroll, "General")

    status = qt_widgets.QLabel()
    status.setObjectName("preferencesStatus")
    status.setWordWrap(True)
    if compact:
        content_layout.insertWidget(1, status)
    else:
        content_layout.addWidget(status)
    binding_status = qt_widgets.QLabel()
    binding_status.setObjectName("bindingStatus")
    binding_status.setAccessibleName("Shortcut registration status")
    binding_status.setTextFormat(qt_core.Qt.PlainText)
    binding_status.setWordWrap(True)
    binding_status.hide()
    if compact:
        content_layout.insertWidget(2, binding_status)
    else:
        content_layout.addWidget(binding_status)
    buttons = qt_widgets.QDialogButtonBox()
    save_button = buttons.addButton("Save", qt_widgets.QDialogButtonBox.AcceptRole)
    apply_button = buttons.addButton("Apply", qt_widgets.QDialogButtonBox.ApplyRole)
    restore_button = buttons.addButton("Restore Defaults", qt_widgets.QDialogButtonBox.ResetRole)
    retry_button = buttons.addButton("Retry shortcuts", qt_widgets.QDialogButtonBox.ActionRole)
    retry_button.setObjectName("retryShortcutsButton")
    retry_button.setAccessibleName("Retry shortcuts")
    retry_button.hide()
    root.addWidget(buttons)
    controller = PreferencesController(
        ctx,
        window,
        shortcut_widgets,
        rows,
        sections,
        status,
        binding_status,
        save_button,
        apply_button,
        retry_button,
        gap_spin,
        cycle_spin,
        almost_spin,
        drag_checkbox,
        launch_checkbox,
    )
    window.controller = controller
    subscribe = getattr(ctx, "subscribe_settings", None)
    if subscribe is not None:
        controller_ref = weakref.ref(controller)
        alive = True

        def on_destroyed(_object=None) -> None:
            nonlocal alive
            alive = False

        def on_settings_changed(_settings: Settings) -> None:
            current = controller_ref()
            if alive and current is not None:
                current._refresh_binding_status()

        window.destroyed.connect(on_destroyed)
        subscribe(on_settings_changed)
    controller.load_settings(ctx.settings)

    def filter_shortcuts(query: str) -> None:
        tokens = query.casefold().split()
        matches = 0
        for name, (label, actions) in sections.items():
            any_visible = False
            for action in actions:
                haystack = f"{name} {action_label(action)}".casefold().replace("sixths", "six")
                visible = all(token in haystack for token in tokens)
                rows[action].setVisible(visible)
                any_visible |= visible
                matches += visible
            label.setVisible(any_visible)
        no_results.setVisible(matches == 0)

    search.textChanged.connect(filter_shortcuts)
    for action, button in shortcut_widgets.items():
        button.clicked.connect(
            lambda _checked=False, selected=action: controller.record_action(selected)
        )
    for control in (gap_spin, cycle_spin, almost_spin, drag_checkbox, launch_checkbox):
        if hasattr(control, "valueChanged"):
            control.valueChanged.connect(controller.mark_dirty)
        else:
            control.toggled.connect(controller.mark_dirty)
    save_button.clicked.connect(lambda: controller.save(close=True))
    apply_button.clicked.connect(lambda: controller.save(close=False))
    retry_button.clicked.connect(controller.retry_shortcuts)

    def restore_defaults():
        for action, button in shortcut_widgets.items():
            combo = _qt_sequence_text(DEFAULT_SHORTCUTS.get(action, ""))
            button.setKeySequence(QtGui.QKeySequence(combo))
        controller.mark_dirty()

    restore_button.clicked.connect(restore_defaults)
    window.setStyleSheet("""
        QDialog#preferencesWindow { background: #f5f7fb; color: #172338; }
        QFrame#brandLogoPanel { background: #172338; border-radius: 8px; }
        QLabel#preferencesHeading { font-family: 'Segoe UI Variable Display', 'Segoe UI';
            font-size: 23px; font-weight: 650; color: #172338; }
        QLabel#sectionHeading { color: #4268a3; font-weight: 700; padding-top: 12px; }
        QFrame#shortcutRow { background: #ffffff; border: 1px solid #dce4f0; border-radius: 6px; }
        QPushButton#shortcutButton { text-align: left; padding-left: 12px; }
        QLabel#preferencesStatus[status="error"] { color: #a52323; }
        QLabel#preferencesStatus[status="warning"] { color: #80540c; }
        QLabel#bindingStatus { background: #fff5df; color: #70480a;
            border: 1px solid #ecd59e; border-radius: 6px; padding: 6px 8px; }
    """)
    return controller
