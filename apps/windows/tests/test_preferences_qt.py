"""Headless Qt tests for the Preferences UI.

These tests exercise the real widgets without requiring a human to click
through the dialog. They skip cleanly when PySide6 is not installed.
"""

from __future__ import annotations

import os
from contextlib import suppress

import pytest
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.shortcuts import normalise
from windows_rectangle.ports.config_store import Settings

from windows_rectangle.ui import preferences

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class SpyConfigStore:
    def __init__(self) -> None:
        self.saved: list[Settings] = []

    def save(self, settings: Settings) -> None:
        self.saved.append(settings)


class SpyHotkeys:
    def __init__(self) -> None:
        self.unregister_all_calls = 0

    def unregister_all(self) -> None:
        self.unregister_all_calls += 1


class SpyContext:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        config_store: SpyConfigStore | None = None,
        hotkeys: SpyHotkeys | None = None,
    ) -> None:
        self.settings = settings if settings is not None else Settings()
        self.config_store = config_store
        self.hotkeys = hotkeys
        self.applied: list[Settings] = []
        self.rebind_calls = 0

    def apply_settings(self, settings: Settings) -> None:
        self.applied.append(settings)
        self.settings = settings

    def rebind_hotkeys(self) -> int:
        self.rebind_calls += 1
        return sum(1 for combo in self.settings.shortcuts.values() if combo.strip())


@pytest.fixture(scope="module")
def qt_modules():
    qt_core = pytest.importorskip("PySide6.QtCore")
    qt_gui = pytest.importorskip("PySide6.QtGui")
    qt_widgets = pytest.importorskip("PySide6.QtWidgets")
    qt_test = pytest.importorskip("PySide6.QtTest")
    return qt_core, qt_gui, qt_widgets, qt_test


@pytest.fixture
def qt_app(qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])
    _forget_singleton_preferences(app)
    yield app
    for widget in list(app.topLevelWidgets()):
        controller = getattr(widget, "controller", None)
        if isinstance(controller, preferences.PreferencesController):
            controller.dirty = False
        widget.hide()
        widget.deleteLater()
    _forget_singleton_preferences(app)
    app.processEvents()


def _forget_singleton_preferences(app) -> None:
    with suppress(AttributeError):
        delattr(app, "_windows_rectangle_preferences")


def _build_controller(qt_app, qt_modules, ctx: SpyContext | None = None):
    qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    controller = preferences._build_window(ctx or SpyContext(), qt_core, qt_widgets)
    controller.window.show()
    qt_app.processEvents()
    return controller


def _row_for_action(controller: preferences.PreferencesController, qt_widgets, action: Action):
    for row in controller.window.findChildren(qt_widgets.QFrame, "shortcutRow"):
        if row.property("action") == action.value:
            return row
    raise AssertionError(f"missing row for {action.value}")


def _button_box_button(controller: preferences.PreferencesController, qt_widgets, text: str):
    box = controller.window.findChild(qt_widgets.QDialogButtonBox)
    assert box is not None
    for button in box.buttons():
        if button.text() == text:
            return button
    raise AssertionError(f"missing dialog button {text!r}")


def _write_test_png(qt_gui, path) -> None:
    pixmap = qt_gui.QPixmap(32, 32)
    pixmap.fill(qt_gui.QColor(220, 20, 60))
    assert pixmap.save(str(path), "PNG")


def test_qt_preferences_window_has_expected_structure(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)

    window = controller.window
    assert window.objectName() == "preferencesWindow"
    assert window.windowTitle() == "Windows Rectangle"
    assert window.minimumWidth() >= 820
    assert window.minimumHeight() >= 620

    tabs = window.findChild(qt_widgets.QTabWidget, "preferencesTabs")
    assert tabs is not None
    assert tabs.count() == 3
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Shortcuts",
        "Layouts",
        "General",
    ]
    layout_button = window.findChild(qt_widgets.QPushButton, "openLayoutsButton")
    assert layout_button is not None
    assert layout_button.text() == "Open Layout Designer"

    search = window.findChild(qt_widgets.QLineEdit, "shortcutSearch")
    assert search is not None
    assert search.placeholderText() == "Search commands"
    assert search.accessibleName() == "Search commands"

    assert set(controller.shortcut_widgets) == set(preferences.ordered_actions())
    for action, button in controller.shortcut_widgets.items():
        assert button.objectName() == "shortcutButton"
        assert button.toolTip() == "Record Shortcut"
        assert button.accessibleName() == f"{preferences.action_label(action)} shortcut"
        assert button.minimumWidth() >= 220
        assert button.minimumHeight() >= 34


def test_qt_preferences_exposes_every_supported_action(qt_app, qt_modules):
    controller = _build_controller(qt_app, qt_modules)
    assert set(controller.shortcut_widgets) == set(Action)


def test_qt_preferences_preserves_saved_workspaces(qt_app, qt_modules):
    settings = Settings(workspaces=("saved-workspace",), active_workspace_id="workspace-1")
    controller = _build_controller(qt_app, qt_modules, SpyContext(settings))

    collected = controller.collect_settings()

    assert collected.workspaces == ("saved-workspace",)
    assert collected.active_workspace_id == "workspace-1"


def test_qt_preferences_window_uses_custom_logo(qt_app, qt_modules, tmp_path, monkeypatch):
    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    logo_dir = tmp_path / "logo"
    logo_dir.mkdir()
    _write_test_png(qt_gui, logo_dir / "logo.png")
    monkeypatch.setenv("WINDOWS_RECTANGLE_LOGO_DIR", str(logo_dir))

    controller = _build_controller(qt_app, qt_modules)

    assert not controller.window.windowIcon().isNull()
    logo_panel = controller.window.findChild(qt_widgets.QFrame, "brandLogoPanel")
    assert logo_panel is not None
    assert logo_panel.accessibleName() == "Application logo"
    assert logo_panel.width() == 56
    assert logo_panel.height() >= 56

    logo_label = controller.window.findChild(qt_widgets.QLabel, "brandLogo")
    assert logo_label is not None
    assert logo_label.accessibleName() == "Application logo image"
    assert logo_label.size() == logo_panel.size()
    assert logo_panel.layout().contentsMargins().left() == 0
    assert logo_label.pixmap() is not None
    assert not logo_label.pixmap().isNull()


def test_qt_preferences_window_renders_non_blank_screenshot(qt_app, qt_modules):
    _qt_core, _qt_gui, _qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)

    pixmap = controller.window.grab()
    assert not pixmap.isNull()
    assert pixmap.width() >= 820
    assert pixmap.height() >= 620

    image = pixmap.toImage()
    sample_points = [
        (10, 10),
        (image.width() // 2, 20),
        (image.width() // 2, image.height() // 2),
        (image.width() - 20, image.height() - 20),
    ]
    sampled_colors = {image.pixelColor(x, y).rgba() for x, y in sample_points}
    assert len(sampled_colors) > 1


def test_qt_shortcut_search_filters_rows_and_sections(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    search = controller.window.findChild(qt_widgets.QLineEdit, "shortcutSearch")
    assert search is not None

    search.setText("six top")
    qt_app.processEvents()

    assert _row_for_action(controller, qt_widgets, Action.TOP_LEFT_SIXTH).isVisible()
    assert _row_for_action(controller, qt_widgets, Action.TOP_RIGHT_SIXTH).isVisible()
    assert not _row_for_action(controller, qt_widgets, Action.LEFT_HALF).isVisible()
    assert not _row_for_action(controller, qt_widgets, Action.BOTTOM_RIGHT_SIXTH).isVisible()

    sections = {
        label.text(): label.isVisible()
        for label in controller.window.findChildren(qt_widgets.QLabel, "sectionHeading")
    }
    assert sections["Sixths"]
    assert not sections["Halves"]

    search.clear()
    qt_app.processEvents()
    rows = controller.window.findChildren(qt_widgets.QFrame, "shortcutRow")
    assert all(row.isVisible() for row in rows)


def test_qt_general_controls_mark_dirty_and_collect_settings(qt_app, qt_modules):
    controller = _build_controller(qt_app, qt_modules)

    controller.gap_spin.setValue(17)
    controller.cycle_spin.setValue(2.4)
    controller.almost_spin.setValue(73)
    controller.drag_checkbox.setChecked(False)
    controller.launch_checkbox.setChecked(True)
    settings = controller.collect_settings()

    assert controller.dirty is True
    assert settings.gap == 17
    assert settings.cycle_idle_timeout == pytest.approx(2.4)
    assert settings.almost_maximize_scale == pytest.approx(0.73)
    assert settings.drag_to_edge_enabled is False
    assert settings.launch_at_login is True


def test_qt_record_button_updates_shortcut_and_restores_hotkeys(qt_app, qt_modules, monkeypatch):
    _qt_core, qt_gui, _qt_widgets, _qt_test = qt_modules
    hotkeys = SpyHotkeys()
    ctx = SpyContext(hotkeys=hotkeys)
    controller = _build_controller(qt_app, qt_modules, ctx)

    def fake_record(_parent, action_name, _qt_core, _qt_gui, _qt_widgets):
        assert action_name == "Left Half"
        return qt_gui.QKeySequence("Ctrl+Alt+L")

    monkeypatch.setattr(preferences, "_record_shortcut", fake_record)

    controller.shortcut_widgets[Action.LEFT_HALF].click()
    qt_app.processEvents()

    assert preferences._sequence_text(controller.shortcut_widgets[Action.LEFT_HALF]) == "Ctrl+Alt+L"
    assert controller.shortcut_widgets[Action.LEFT_HALF].text() == "Ctrl+Alt+L"
    assert controller.dirty is True
    assert hotkeys.unregister_all_calls == 1
    assert ctx.rebind_calls == 1


def test_qt_record_cancel_preserves_shortcut_and_clean_state(qt_app, qt_modules, monkeypatch):
    ctx = SpyContext()
    controller = _build_controller(qt_app, qt_modules, ctx)
    button = controller.shortcut_widgets[Action.LEFT_HALF]
    original = preferences._sequence_text(button)
    monkeypatch.setattr(preferences, "_record_shortcut", lambda *_args: None)

    button.click()
    qt_app.processEvents()

    assert preferences._sequence_text(button) == original
    assert controller.dirty is False
    assert ctx.rebind_calls == 0


def test_qt_duplicate_shortcuts_disable_save_and_apply(qt_app, qt_modules):
    _qt_core, qt_gui, _qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    duplicate = qt_gui.QKeySequence("Ctrl+Alt+L")
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(duplicate)
    controller.shortcut_widgets[Action.RIGHT_HALF].setKeySequence(duplicate)

    controller.mark_dirty()

    assert controller.status_label.property("status") == "error"
    assert "duplicates" in controller.status_label.text()
    assert not controller.save_button.isEnabled()
    assert not controller.apply_button.isEnabled()


def test_qt_reserved_shortcut_warns_but_still_allows_save(qt_app, qt_modules):
    _qt_core, qt_gui, _qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(qt_gui.QKeySequence("Meta+Left"))

    controller.mark_dirty()

    assert controller.status_label.property("status") == "warning"
    assert "reserved" in controller.status_label.text()
    assert controller.save_button.isEnabled()
    assert controller.apply_button.isEnabled()


def test_qt_save_applies_persists_rebinds_and_hides_window(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    config = SpyConfigStore()
    ctx = SpyContext(config_store=config)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)

    _button_box_button(controller, qt_widgets, "Save").click()
    qt_app.processEvents()

    assert len(config.saved) == 1
    assert config.saved[0].gap == 18
    assert ctx.applied[0].gap == 18
    assert ctx.rebind_calls == 0
    assert controller.dirty is False
    assert not controller.window.isVisible()


def test_qt_apply_persists_without_closing_window(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    config = SpyConfigStore()
    ctx = SpyContext(config_store=config)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.cycle_spin.setValue(3.0)

    _button_box_button(controller, qt_widgets, "Apply").click()
    qt_app.processEvents()

    assert config.saved[0].cycle_idle_timeout == pytest.approx(3.0)
    assert ctx.applied[0].cycle_idle_timeout == pytest.approx(3.0)
    assert controller.dirty is False
    assert controller.window.isVisible()


def test_qt_restore_defaults_resets_shortcuts_and_marks_dirty(qt_app, qt_modules):
    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(qt_gui.QKeySequence("Ctrl+Alt+L"))
    controller.dirty = False

    _button_box_button(controller, qt_widgets, "Restore Defaults").click()
    qt_app.processEvents()

    restored = preferences._sequence_text(controller.shortcut_widgets[Action.LEFT_HALF])
    assert normalise(restored) == DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    assert controller.dirty is True


def test_qt_show_reuses_existing_clean_window_and_refreshes(qt_app, qt_modules):
    ctx = SpyContext(Settings(gap=4))
    first = preferences.show(ctx)
    qt_app.processEvents()

    ctx.settings = Settings(gap=22)
    second = preferences.show(ctx)
    qt_app.processEvents()

    assert second is first
    assert second.gap_spin.value() == 22


def test_qt_show_does_not_clobber_dirty_existing_window(qt_app, qt_modules):
    ctx = SpyContext(Settings(gap=4))
    first = preferences.show(ctx)
    qt_app.processEvents()
    first.gap_spin.setValue(9)
    assert first.dirty is True

    ctx.settings = Settings(gap=22)
    second = preferences.show(ctx)
    qt_app.processEvents()

    assert second is first
    assert second.gap_spin.value() == 9


def test_qt_record_dialog_clear_returns_disabled_sequence(qt_app, qt_modules):
    qt_core, qt_gui, qt_widgets, _qt_test = qt_modules

    def click_clear() -> None:
        dialog = next(
            widget
            for widget in qt_app.topLevelWidgets()
            if widget.objectName() == "recordShortcutDialog"
        )
        clear = next(
            button
            for button in dialog.findChildren(qt_widgets.QPushButton)
            if button.text() == "Clear"
        )
        clear.click()

    qt_core.QTimer.singleShot(0, click_clear)

    sequence = preferences._record_shortcut(None, "Left Half", qt_core, qt_gui, qt_widgets)

    assert sequence is not None
    assert sequence.toString(qt_gui.QKeySequence.PortableText) == ""


def test_qt_record_dialog_accepts_keyboard_sequence(qt_app, qt_modules):
    qt_core, qt_gui, qt_widgets, qt_test = qt_modules

    def type_shortcut() -> None:
        dialog = next(
            widget
            for widget in qt_app.topLevelWidgets()
            if widget.objectName() == "recordShortcutDialog"
        )
        editor = dialog.findChild(qt_widgets.QKeySequenceEdit, "recordShortcutEditor")
        assert editor is not None
        editor.setFocus()
        qt_test.QTest.keyClick(
            editor,
            qt_core.Qt.Key_L,
            qt_core.Qt.ControlModifier | qt_core.Qt.AltModifier,
        )
        qt_core.QTimer.singleShot(500, dialog.accept)

    qt_core.QTimer.singleShot(50, type_shortcut)

    sequence = preferences._record_shortcut(None, "Left Half", qt_core, qt_gui, qt_widgets)

    assert sequence is not None
    assert sequence.toString(qt_gui.QKeySequence.PortableText) == "Ctrl+Alt+L"
