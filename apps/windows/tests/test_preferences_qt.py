"""Headless Qt tests for the Preferences UI.

These tests exercise the real widgets without requiring a human to click
through the dialog. They skip cleanly when PySide6 is not installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from textwrap import dedent

import pytest

from windows_rectangle.app import EMPTY_BINDING_REPORT, BindingReport, bind_hotkeys_via_bus, build
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.shortcuts import normalise
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui import preferences

from .conftest import FakeWindowManager

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
        self.last_binding_report = EMPTY_BINDING_REPORT
        self.next_binding_report: BindingReport | None = None
        self.settings_at_rebind: list[Settings] = []
        self.paused = False

    def apply_settings(self, settings: Settings) -> None:
        self.applied.append(settings)
        self.settings = settings

    def rebind_hotkeys(self) -> int:
        self.rebind_calls += 1
        self.settings_at_rebind.append(deepcopy(self.settings))
        if self.next_binding_report is not None:
            self.last_binding_report = self.next_binding_report
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


def _failed_binding_report(*, paused: bool = False) -> BindingReport:
    return BindingReport(
        failed=((Action.LEFT_HALF, "ctrl+alt+left", "already registered"),), paused=paused
    )


def _real_context_with_failed_hotkey():
    class FakeHotkeys:
        def __init__(self) -> None:
            self.reject = True
            self.registered: list[str] = []

        def register(self, combo, _callback):
            if self.reject and combo == "ctrl+alt+left":
                raise RuntimeError("already registered")
            self.registered.append(combo)
            return len(self.registered)

        def unregister_all(self) -> None:
            self.registered.clear()

    hotkeys = FakeHotkeys()
    ctx = build(Settings(), FakeWindowManager(), hotkeys=hotkeys)
    bind_hotkeys_via_bus(ctx, hotkeys.register)
    assert ctx.last_binding_report.failed_count == 1
    return ctx, hotkeys


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

    tabs = window.findChild(qt_widgets.QTabWidget, "preferencesTabs")
    assert tabs is not None
    assert tabs.count() == 2
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Shortcuts", "General"]

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
    assert logo_panel.width() >= 196
    assert logo_panel.height() >= 56

    logo_label = controller.window.findChild(qt_widgets.QLabel, "brandLogo")
    assert logo_label is not None
    assert logo_label.accessibleName() == "Application logo image"
    assert logo_label.pixmap() is not None
    assert not logo_label.pixmap().isNull()


def test_qt_preferences_window_renders_non_blank_screenshot(qt_app, qt_modules):
    _qt_core, _qt_gui, _qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)

    pixmap = controller.window.grab()
    assert not pixmap.isNull()
    assert pixmap.width() >= 600
    assert pixmap.height() >= 400

    image = pixmap.toImage()
    sample_points = [
        (10, 10),
        (image.width() // 2, 20),
        (image.width() // 2, image.height() // 2),
        (image.width() - 20, image.height() - 20),
    ]
    sampled_colors = {image.pixelColor(x, y).rgba() for x, y in sample_points}
    assert len(sampled_colors) > 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop scaling")
def test_qt_preferences_buttons_fit_scaled_desktop():
    script = dedent("""
        import json
        from PySide6 import QtCore, QtWidgets
        from windows_rectangle.app import BindingReport
        from windows_rectangle.ports.config_store import Settings
        from windows_rectangle.ui.preferences import _build_window, ordered_actions
        class Context:
            settings = Settings()
            config_store = None
        app = QtWidgets.QApplication([])
        controller = _build_window(Context(), QtCore, QtWidgets)
        controller.window.show()
        app.processEvents()
        screen = controller.window.screen().availableGeometry()
        frame = controller.window.frameGeometry()
        apply = controller.apply_button
        apply_bottom = apply.mapToGlobal(QtCore.QPoint(apply.width() - 1, apply.height() - 1))
        print(json.dumps({
            "screen": [screen.x(), screen.y(), screen.width(), screen.height()],
            "frame": [frame.x(), frame.y(), frame.width(), frame.height()],
            "frame_fits": screen.contains(frame),
            "apply_fits": screen.contains(apply_bottom),
        }))
        controller.window.close()

        class SizedWidgets:
            class QApplication:
                @staticmethod
                def primaryScreen():
                    class Screen:
                        @staticmethod
                        def availableGeometry():
                            return QtCore.QRect(0, 0, 512, 360)
                    return Screen()

            def __getattr__(self, name):
                return getattr(QtWidgets, name)

        class FailedContext(Context):
            last_binding_report = BindingReport(failed=tuple(
                (action, "ctrl+alt+left", "already registered")
                for action in list(ordered_actions())[:5]
            ))

        narrow = _build_window(FailedContext(), QtCore, SizedWidgets())
        narrow.window.show()
        app.processEvents()
        frame = narrow.window.frameGeometry()
        buttons = narrow.window.findChild(QtWidgets.QDialogButtonBox)
        print(json.dumps({
            "narrow_frame": [frame.width(), frame.height()],
            "narrow_actions_fit": all(
                narrow.window.rect().contains(
                    button.mapTo(narrow.window, QtCore.QPoint(button.width() - 1, button.height() - 1))
                ) for button in buttons.buttons() if button.isVisible()
            ),
        }))
        narrow.window.close()
    """)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "windows"
    env["QT_SCALE_FACTOR"] = "2"
    package_dir = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = str(package_dir) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=30,
    )
    geometry, narrow = (json.loads(line) for line in result.stdout.splitlines())

    assert geometry["frame_fits"], geometry
    assert geometry["apply_fits"], geometry
    assert narrow["narrow_frame"][0] <= 512, narrow
    assert narrow["narrow_frame"][1] <= 360, narrow
    assert narrow["narrow_actions_fit"], narrow


@pytest.mark.parametrize("failed_count", [0, 5])
def test_qt_preferences_fit_512_by_360_available_screen(qt_app, qt_modules, failed_count):
    qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules

    class SizedWidgets:
        class QApplication:
            @staticmethod
            def primaryScreen():
                class Screen:
                    @staticmethod
                    def availableGeometry():
                        return qt_core.QRect(0, 0, 512, 360)

                return Screen()

        def __getattr__(self, name):
            return getattr(qt_widgets, name)

    ctx = SpyContext()
    if failed_count:
        ctx.last_binding_report = BindingReport(
            failed=tuple(
                (action, "ctrl+alt+left", "already registered")
                for action in list(preferences.ordered_actions())[:failed_count]
            )
        )
    controller = preferences._build_window(ctx, qt_core, SizedWidgets())
    window = controller.window
    window.show()
    qt_app.processEvents()

    assert window.frameGeometry().width() <= 512
    assert window.frameGeometry().height() <= 360
    for text in ("Save", "Apply", "Restore Defaults") + (
        ("Retry shortcuts",) if failed_count else ()
    ):
        button = _button_box_button(controller, qt_widgets, text)
        bottom_right = button.mapTo(window, qt_core.QPoint(button.width() - 1, button.height() - 1))
        assert button.isVisible()
        assert window.rect().contains(bottom_right), text
    if failed_count:
        content_scroll = window.findChild(qt_widgets.QScrollArea, "preferencesContentScroll")
        warning_center = controller.binding_status_label.mapTo(
            content_scroll.viewport(), controller.binding_status_label.rect().center()
        )
        assert content_scroll.viewport().rect().contains(warning_center)

    tabs = window.findChild(qt_widgets.QTabWidget, "preferencesTabs")
    assert tabs.height() <= 200
    tabs.setCurrentIndex(1)
    qt_app.processEvents()
    general_scroll = window.findChild(qt_widgets.QScrollArea, "generalScroll")
    assert general_scroll is not None
    content_scroll = window.findChild(qt_widgets.QScrollArea, "preferencesContentScroll")
    for control in (controller.gap_spin, controller.cycle_spin, controller.launch_checkbox):
        general_scroll.ensureWidgetVisible(control)
        content_scroll.ensureWidgetVisible(control)
        qt_app.processEvents()
        center = control.mapTo(general_scroll.viewport(), control.rect().center())
        assert general_scroll.viewport().rect().contains(center), control.objectName()
        outer_center = control.mapTo(content_scroll.viewport(), control.rect().center())
        assert content_scroll.viewport().rect().contains(outer_center), control.objectName()


def test_qt_general_values_show_units(qt_app, qt_modules):
    controller = _build_controller(qt_app, qt_modules)
    assert controller.gap_spin.suffix() == " px"
    assert controller.cycle_spin.suffix() == " s"


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


def test_qt_search_explains_no_results_and_supports_keyboard(qt_app, qt_modules):
    qt_core, _qt_gui, qt_widgets, qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    search = controller.window.findChild(qt_widgets.QLineEdit, "shortcutSearch")
    empty = controller.window.findChild(qt_widgets.QLabel, "noShortcutsFound")
    assert empty is not None

    qt_test.QTest.keyClick(controller.window, qt_core.Qt.Key_F, qt_core.Qt.ControlModifier)
    assert search.hasFocus()
    qt_test.QTest.keyClicks(search, "no-matching-command")
    qt_app.processEvents()
    assert empty.isVisible()
    assert "no" in empty.text().casefold()
    assert not any(row.isVisible() for row in controller.rows.values())

    qt_test.QTest.keyClick(search, qt_core.Qt.Key_Escape)
    qt_app.processEvents()
    assert search.text() == ""
    assert not empty.isVisible()
    assert controller.window.isVisible()

    tabs = controller.window.findChild(qt_widgets.QTabWidget, "preferencesTabs")
    tabs.setCurrentIndex(1)
    controller.gap_spin.setFocus()
    qt_test.QTest.keyClick(controller.gap_spin, qt_core.Qt.Key_F, qt_core.Qt.ControlModifier)
    qt_app.processEvents()
    assert tabs.currentIndex() == 0
    assert search.hasFocus()


def test_qt_escape_outside_search_closes_window(qt_app, qt_modules):
    qt_core, _qt_gui, qt_widgets, qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    tabs = controller.window.findChild(qt_widgets.QTabWidget, "preferencesTabs")
    tabs.setCurrentIndex(1)
    controller.gap_spin.setFocus()

    qt_test.QTest.keyClick(controller.gap_spin, qt_core.Qt.Key_Escape)
    qt_app.processEvents()

    assert not controller.window.isVisible()


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


def test_qt_reverting_general_edit_restores_clean_state(qt_app, qt_modules):
    ctx = SpyContext(Settings(gap=4))
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)
    assert controller.apply_button.isEnabled()

    controller.gap_spin.setValue(4)

    assert controller.dirty is False
    assert controller.status_label.text() == "All changes saved"
    assert not controller.save_button.isEnabled()
    assert not controller.apply_button.isEnabled()


@pytest.mark.parametrize("timeout", [0.123, 0.125, 3.45678])
def test_qt_unedited_precise_timeout_survives_other_changes(qt_app, qt_modules, timeout):
    config = SpyConfigStore()
    ctx = SpyContext(Settings(gap=4, cycle_idle_timeout=timeout), config_store=config)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)
    controller.gap_spin.setValue(4)
    assert controller.dirty is False
    assert not controller.apply_button.isEnabled()

    controller.gap_spin.setValue(18)
    controller.save(close=False)

    assert config.saved[0].cycle_idle_timeout == timeout


def test_qt_unedited_mixed_case_shortcut_survives_other_changes(qt_app, qt_modules):
    config = SpyConfigStore()
    settings = Settings(gap=4)
    settings.shortcuts[Action.LEFT_HALF] = "Ctrl+Alt+L"
    controller = _build_controller(qt_app, qt_modules, SpyContext(settings, config_store=config))
    controller.gap_spin.setValue(18)
    controller.gap_spin.setValue(4)
    assert controller.dirty is False
    assert not controller.apply_button.isEnabled()

    controller.gap_spin.setValue(18)
    controller.save(close=False)

    assert config.saved[0].shortcuts[Action.LEFT_HALF] == "Ctrl+Alt+L"


def test_qt_mixed_case_win_and_pageup_shortcuts_display_and_clear(qt_app, qt_modules):
    _qt_core, qt_gui, _qt_widgets, _qt_test = qt_modules
    config = SpyConfigStore()
    settings = Settings()
    settings.shortcuts[Action.LEFT_HALF] = "Win+L"
    settings.shortcuts[Action.TOP_RIGHT_SIXTH] = "Ctrl+PageUp"
    controller = _build_controller(qt_app, qt_modules, SpyContext(settings, config_store=config))
    left = controller.shortcut_widgets[Action.LEFT_HALF]
    right = controller.shortcut_widgets[Action.TOP_RIGHT_SIXTH]

    assert preferences._sequence_text(left), "Win shortcut was blank in the editor"
    assert preferences._sequence_text(right), "PageUp shortcut was blank in the editor"
    assert normalise(preferences._sequence_text(left)) == "win+l"
    assert normalise(preferences._sequence_text(right)) == "ctrl+pgup"
    left.setKeySequence(qt_gui.QKeySequence())
    controller.mark_dirty()
    assert controller.apply_button.isEnabled(), controller.status_label.text()

    controller.save(close=False)

    assert Action.LEFT_HALF not in config.saved[0].shortcuts
    assert config.saved[0].shortcuts[Action.TOP_RIGHT_SIXTH] == "Ctrl+PageUp"


def test_qt_reverting_shortcut_edit_restores_clean_state(qt_app, qt_modules):
    _qt_core, qt_gui, _qt_widgets, _qt_test = qt_modules
    controller = _build_controller(qt_app, qt_modules)
    button = controller.shortcut_widgets[Action.LEFT_HALF]
    original = button.keySequence()
    button.setKeySequence(qt_gui.QKeySequence("Ctrl+Alt+L"))
    controller.mark_dirty()
    assert controller.apply_button.isEnabled()

    button.setKeySequence(original)
    controller.mark_dirty()

    assert controller.dirty is False
    assert not controller.apply_button.isEnabled()


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


def test_qt_save_general_settings_skips_rebind_and_hides_window(qt_app, qt_modules):
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


def test_qt_save_retries_previous_binding_failure(qt_app, qt_modules):
    ctx = SpyContext()
    ctx.last_binding_report = _failed_binding_report()
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)

    controller.save(close=False)

    assert ctx.rebind_calls == 1


def test_qt_failed_binding_visible_retry_uses_saved_settings(qt_app, qt_modules):
    qt_core, _qt_gui, qt_widgets, qt_test = qt_modules
    config = SpyConfigStore()
    ctx = SpyContext(config_store=config)
    ctx.last_binding_report = _failed_binding_report()
    controller = _build_controller(qt_app, qt_modules, ctx)
    binding_status = controller.window.findChild(qt_widgets.QLabel, "bindingStatus")
    retry = controller.window.findChild(qt_widgets.QPushButton, "retryShortcutsButton")

    assert controller.status_label.text() == "All changes saved"
    assert binding_status is not None and binding_status.isVisible()
    assert "1 shortcut unavailable" in binding_status.text()
    assert "Left Half" in binding_status.text()
    assert "ctrl+alt+left" in binding_status.text()
    assert "already registered" in binding_status.text()
    assert retry is not None and retry.isVisible() and retry.isEnabled()
    assert retry.accessibleName() == "Retry shortcuts"

    controller.gap_spin.setValue(18)
    retry.click()
    qt_app.processEvents()

    assert ctx.rebind_calls == 1
    assert ctx.settings_at_rebind[0].gap == 0
    assert ctx.settings.gap == 0
    assert config.saved == []
    assert ctx.applied == []
    assert controller.gap_spin.value() == 18
    assert controller.status_label.text() == "Unsaved changes"
    assert binding_status.isVisible()

    ctx.next_binding_report = BindingReport(bound=((Action.LEFT_HALF, "ctrl+alt+left"),))
    retry.setFocus()
    qt_test.QTest.keyClick(retry, qt_core.Qt.Key_Space)
    qt_app.processEvents()

    assert ctx.rebind_calls == 2
    assert not binding_status.isVisible()
    assert not retry.isVisible()
    assert controller.dirty is True


def test_qt_retry_keeps_shortcut_validation_error(qt_app, qt_modules):
    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    ctx = SpyContext()
    ctx.last_binding_report = _failed_binding_report()
    ctx.next_binding_report = BindingReport()
    controller = _build_controller(qt_app, qt_modules, ctx)
    duplicate = qt_gui.QKeySequence("Ctrl+Alt+L")
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(duplicate)
    controller.shortcut_widgets[Action.RIGHT_HALF].setKeySequence(duplicate)
    controller.mark_dirty()
    assert controller.status_label.property("status") == "error"

    _button_box_button(controller, qt_widgets, "Retry shortcuts").click()

    assert controller.status_label.property("status") == "error"
    assert "duplicates" in controller.status_label.text()
    assert not controller.apply_button.isEnabled()
    assert controller.dirty is True


def test_qt_retry_keeps_save_error(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules

    class FailingStore:
        def save(self, _settings: Settings) -> None:
            raise OSError("disk full")

    ctx = SpyContext(config_store=FailingStore())
    ctx.last_binding_report = _failed_binding_report()
    ctx.next_binding_report = BindingReport()
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)
    controller.save(close=False)
    assert controller.status_label.property("status") == "error"
    assert "disk full" in controller.status_label.text()

    _button_box_button(controller, qt_widgets, "Retry shortcuts").click()

    assert controller.status_label.property("status") == "error"
    assert "disk full" in controller.status_label.text()
    assert controller.dirty is True
    assert ctx.settings.gap == 0


def test_qt_binding_failure_displays_markup_as_literal_text(qt_app, qt_modules):
    qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    ctx = SpyContext()
    ctx.last_binding_report = BindingReport(
        workspace_failed=(("office", "<b>Office</b>", "ctrl+alt+o", "<i>blocked</i>"),)
    )
    controller = _build_controller(qt_app, qt_modules, ctx)
    binding_status = controller.window.findChild(qt_widgets.QLabel, "bindingStatus")

    assert binding_status.textFormat() == qt_core.Qt.PlainText
    assert "<b>Office</b>" in binding_status.text()
    assert "<i>blocked</i>" in binding_status.text()
    assert "&lt;b&gt;Office&lt;/b&gt;" in binding_status.toolTip()
    assert "&lt;i&gt;blocked&lt;/i&gt;" in binding_status.toolTip()
    assert "<b>Office</b>" in binding_status.accessibleDescription()


def test_qt_retry_is_disabled_while_shortcuts_paused(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    ctx = SpyContext()
    ctx.paused = True
    ctx.last_binding_report = _failed_binding_report(paused=True)
    controller = _build_controller(qt_app, qt_modules, ctx)
    binding_status = controller.window.findChild(qt_widgets.QLabel, "bindingStatus")
    retry = controller.window.findChild(qt_widgets.QPushButton, "retryShortcutsButton")

    assert binding_status.isVisible()
    assert "paused" in binding_status.text().casefold()
    assert not retry.isEnabled()
    controller.retry_shortcuts()
    assert ctx.rebind_calls == 0
    assert ctx.last_binding_report.failed_count == 1


def test_qt_general_save_while_paused_keeps_failed_binding_visible(qt_app, qt_modules):
    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    ctx = SpyContext()
    ctx.paused = True
    ctx.last_binding_report = _failed_binding_report(paused=True)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)

    controller.save(close=False)

    assert ctx.settings.gap == 18
    assert ctx.rebind_calls == 0
    assert ctx.last_binding_report.failed_count == 1
    assert controller.window.findChild(qt_widgets.QLabel, "bindingStatus").isVisible()


def test_qt_tray_pause_resume_refreshes_live_binding_feedback_without_losing_edits(
    qt_app, qt_modules, caplog
):
    qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    ctx, hotkeys = _real_context_with_failed_hotkey()
    controller = _build_controller(qt_app, qt_modules, ctx)
    binding_status = controller.window.findChild(qt_widgets.QLabel, "bindingStatus")
    retry = controller.window.findChild(qt_widgets.QPushButton, "retryShortcutsButton")
    controller.gap_spin.setValue(18)

    assert ctx.pause_hotkeys() is True
    qt_app.processEvents()

    assert "paused" in binding_status.text().casefold()
    assert not retry.isEnabled()
    assert controller.gap_spin.value() == 18
    assert controller.dirty is True
    assert controller.status_label.text() == "Unsaved changes"

    hotkeys.reject = False
    assert ctx.resume_hotkeys() is True
    qt_app.processEvents()

    assert not binding_status.isVisible()
    assert not retry.isVisible()
    assert controller.gap_spin.value() == 18
    assert controller.status_label.text() == "Unsaved changes"

    controller.window.deleteLater()
    qt_core.QCoreApplication.sendPostedEvents(None, qt_core.QEvent.DeferredDelete)
    ctx.pause_hotkeys()
    assert "settings subscriber raised" not in caplog.text


def test_qt_save_stays_open_when_os_rejects_saved_shortcut(qt_app, qt_modules):
    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    config = SpyConfigStore()

    class FailingBindContext(SpyContext):
        def apply_settings(self, settings: Settings) -> None:
            super().apply_settings(settings)
            self.last_binding_report = _failed_binding_report()

    ctx = FailingBindContext(config_store=config)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(qt_gui.QKeySequence("Ctrl+Alt+L"))
    controller.mark_dirty()

    _button_box_button(controller, qt_widgets, "Save").click()
    qt_app.processEvents()

    assert len(config.saved) == 1
    assert controller.dirty is False
    assert controller.status_label.text() == "All changes saved"
    assert controller.window.isVisible()
    assert controller.window.findChild(qt_widgets.QLabel, "bindingStatus").isVisible()


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


def test_qt_apply_preserves_newer_tray_setting_and_workspace(qt_app, qt_modules, tmp_path):
    from windows_rectangle.adapters.json_config import JsonConfigStore
    from windows_rectangle.core.workspaces import Workspace

    _qt_core, _qt_gui, qt_widgets, _qt_test = qt_modules
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(Settings(gap=4, launch_at_login=False))
    ctx = SpyContext(store.load(), config_store=store)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.gap_spin.setValue(18)

    current = store.load()
    current.launch_at_login = True
    current.workspaces = (Workspace("office", "Office", ()),)
    store.save(current)
    ctx.settings = current

    _button_box_button(controller, qt_widgets, "Apply").click()
    saved = store.load()
    assert saved.gap == 18
    assert saved.launch_at_login is True
    assert saved.workspaces[0].id == "office"
    assert controller.launch_checkbox.isChecked()


def test_qt_apply_merges_only_edited_shortcut(qt_app, qt_modules, tmp_path):
    from windows_rectangle.adapters.json_config import JsonConfigStore

    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    store = JsonConfigStore(tmp_path / "config.json")
    store.save(Settings())
    ctx = SpyContext(store.load(), config_store=store)
    controller = _build_controller(qt_app, qt_modules, ctx)
    controller.shortcut_widgets[Action.LEFT_HALF].setKeySequence(qt_gui.QKeySequence("Ctrl+Alt+L"))
    controller.mark_dirty()

    current = store.load()
    current.shortcuts[Action.RIGHT_HALF] = "ctrl+shift+right"
    store.save(current)
    ctx.settings = current

    _button_box_button(controller, qt_widgets, "Apply").click()
    saved = store.load()
    assert saved.shortcuts[Action.LEFT_HALF] == "ctrl+alt+l"
    assert saved.shortcuts[Action.RIGHT_HALF] == "ctrl+shift+right"


def test_qt_restore_defaults_resets_shortcuts_and_marks_dirty(qt_app, qt_modules):
    _qt_core, qt_gui, qt_widgets, _qt_test = qt_modules
    settings = Settings()
    settings.shortcuts[Action.LEFT_HALF] = "ctrl+alt+l"
    controller = _build_controller(qt_app, qt_modules, SpyContext(settings))

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
