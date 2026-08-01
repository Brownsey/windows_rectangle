"""Tests for windows_rectangle.ui.preferences."""

from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui import preferences


class FakeStyle:
    def unpolish(self, _widget):
        pass

    def polish(self, _widget):
        pass


class FakeStatusLabel:
    def __init__(self):
        self.text = ""
        self.properties = {}

    def setText(self, text):
        self.text = text

    def setProperty(self, name, value):
        self.properties[name] = value

    def style(self):
        return FakeStyle()


class FakeButton:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, enabled):
        self.enabled = enabled


def test_preferences_module_imports_without_pyside6():
    assert preferences.PreferencesController is not None
    assert preferences.show is not None


def test_validate_default_shortcuts_ok():
    result = preferences.validate_shortcuts(dict(DEFAULT_SHORTCUTS))
    assert result.ok
    assert result.errors == ()


def test_validate_shortcuts_rejects_duplicates():
    shortcuts = {
        Action.LEFT_HALF: "ctrl+alt+left",
        Action.RIGHT_HALF: "Ctrl + Alt + Left",
    }
    result = preferences.validate_shortcuts(shortcuts)
    assert not result.ok
    assert "duplicates" in result.errors[0]


def test_validate_shortcuts_rejects_unsupported_keys():
    result = preferences.validate_shortcuts({Action.LEFT_HALF: "ctrl+alt+volumeup"})
    assert not result.ok
    assert "no Win32 vkey" in result.errors[0]


def test_validate_shortcuts_warns_on_reserved_combo():
    result = preferences.validate_shortcuts({Action.LEFT_HALF: "win+left"})
    assert result.ok
    assert "reserved" in result.warnings[0]


def test_validate_shortcuts_allows_blank_to_disable_command():
    result = preferences.validate_shortcuts(
        {
            Action.LEFT_HALF: "",
            Action.RIGHT_HALF: "   ",
            Action.MAXIMIZE: "ctrl+alt+enter",
        }
    )
    assert result.ok
    assert result.errors == ()


def test_normalise_settings_canonicalises_and_clamps_values():
    settings = Settings(
        shortcuts={Action.LEFT_HALF: "Control + Alt + LEFT"},
        gap=-5,
        cycle_idle_timeout=0,
        almost_maximize_scale=2.0,
    )
    normalised = preferences.normalise_settings(settings)
    assert normalised.shortcuts[Action.LEFT_HALF] == "ctrl+alt+left"
    assert normalised.gap == 0
    assert normalised.cycle_idle_timeout == 0.1
    assert normalised.almost_maximize_scale == 1.0


def test_normalise_settings_preserves_blank_disabled_shortcut():
    normalised = preferences.normalise_settings(Settings(shortcuts={Action.LEFT_HALF: "  "}))
    assert normalised.shortcuts[Action.LEFT_HALF] == ""


def test_shortcut_button_text_formats_recorded_combo():
    assert preferences._shortcut_button_text("ctrl+alt+left") == "Ctrl+Alt+Left"
    assert preferences._shortcut_button_text("ctrl+win+pageup") == "Ctrl+Win+Pg Up"


def test_shortcut_button_text_marks_blank_combo_disabled():
    assert preferences._shortcut_button_text("") == "Disabled"


def test_status_text_shows_saved_and_enabled_count():
    shortcuts = {
        Action.LEFT_HALF: "ctrl+win+left",
        Action.RIGHT_HALF: "",
    }
    assert preferences._status_text(False, shortcuts) == "Saved - 1 shortcut enabled"
    assert preferences._status_text(True, shortcuts) == "Unsaved changes - 1 shortcut enabled"


def test_shortcut_filter_matches_group_and_action_terms():
    assert preferences._matches_shortcut_filter("Left Half", "Halves", "left")
    assert preferences._matches_shortcut_filter("Top Right 3/6", "Sixths", "six top")
    assert not preferences._matches_shortcut_filter("Left Half", "Halves", "right")


def test_update_validation_tracks_dirty_status_and_apply_state():
    class FakeSequence:
        def toString(self, _mode):
            return "Ctrl+Alt+Left"

    class FakeShortcutWidget:
        def keySequence(self):
            return FakeSequence()

    class FakeCtx:
        settings = Settings(shortcuts={Action.LEFT_HALF: DEFAULT_SHORTCUTS[Action.LEFT_HALF]})

    controller = preferences.PreferencesController(
        ctx=FakeCtx(),
        window=object(),
        shortcut_widgets={Action.LEFT_HALF: FakeShortcutWidget()},
        status_label=FakeStatusLabel(),
        save_button=FakeButton(),
        apply_button=FakeButton(),
    )

    controller.update_validation()

    assert controller.status_label.text == "Saved - 1 shortcut enabled"
    assert controller.status_label.properties["status"] == "saved"
    assert controller.save_button.enabled is True
    assert controller.apply_button.enabled is False

    controller.mark_dirty()

    assert controller.status_label.text == "Unsaved changes - 1 shortcut enabled"
    assert controller.status_label.properties["status"] == "dirty"
    assert controller.apply_button.enabled is True


def test_mark_dirty_is_ignored_while_loading():
    class FakeCtx:
        settings = Settings()

    controller = preferences.PreferencesController(ctx=FakeCtx(), window=object(), _loading=True)

    controller.mark_dirty()

    assert controller.dirty is False


def test_confirm_discard_allows_clean_close_without_prompt():
    class FakeMessageBox:
        prompt_count = 0
        Yes = 1
        No = 2

        @classmethod
        def question(cls, *_args):
            cls.prompt_count += 1
            return cls.No

    class FakeQtWidgets:
        QMessageBox = FakeMessageBox

    controller = preferences.PreferencesController(ctx=object(), window=object(), dirty=False)

    assert preferences._confirm_discard_if_dirty(controller, FakeQtWidgets) is True
    assert FakeMessageBox.prompt_count == 0


def test_confirm_discard_uses_user_choice_when_dirty():
    class FakeMessageBox:
        Yes = 1
        No = 2

        @classmethod
        def question(cls, *_args):
            return cls.Yes

    class FakeQtWidgets:
        QMessageBox = FakeMessageBox

    controller = preferences.PreferencesController(ctx=object(), window=object(), dirty=True)

    assert preferences._confirm_discard_if_dirty(controller, FakeQtWidgets) is True


def test_suspend_hotkeys_for_recording_is_noop_without_hotkeys():
    class FakeCtx:
        hotkeys = None

    controller = preferences.PreferencesController(ctx=FakeCtx(), window=object())

    assert preferences._suspend_hotkeys_for_recording(controller) is False


def test_suspend_hotkeys_for_recording_unregisters_current_hotkeys():
    class FakeHotkeys:
        def __init__(self):
            self.unregister_all_calls = 0

        def unregister_all(self):
            self.unregister_all_calls += 1

    class FakeCtx:
        def __init__(self):
            self.hotkeys = FakeHotkeys()

    ctx = FakeCtx()
    controller = preferences.PreferencesController(ctx=ctx, window=object())

    assert preferences._suspend_hotkeys_for_recording(controller) is True
    assert ctx.hotkeys.unregister_all_calls == 1


def test_apply_invalid_shortcut_returns_false_without_saving():
    class FakeSequence:
        def toString(self, _mode):
            return "Ctrl+Alt+VolumeUp"

    class FakeShortcutWidget:
        def keySequence(self):
            return FakeSequence()

        def setKeySequence(self, _sequence):
            pass

    class FakeCtx:
        settings = Settings(shortcuts={Action.LEFT_HALF: DEFAULT_SHORTCUTS[Action.LEFT_HALF]})
        config_store = None

        def apply_settings(self, settings):
            raise AssertionError("invalid settings should not be applied")

        def rebind_hotkeys(self):
            raise AssertionError("invalid settings should not rebind hotkeys")

    controller = preferences.PreferencesController(
        ctx=FakeCtx(),
        window=object(),
        shortcut_widgets={Action.LEFT_HALF: FakeShortcutWidget()},
    )

    assert controller.apply() is False


def test_apply_blank_shortcut_saves_and_rebinds():
    saved = []
    applied = []

    class FakeSequence:
        def toString(self, _mode):
            return ""

    class FakeShortcutWidget:
        def keySequence(self):
            return FakeSequence()

        def setKeySequence(self, _sequence):
            pass

    class FakeConfigStore:
        def save(self, settings):
            saved.append(settings)

    class FakeCtx:
        settings = Settings(shortcuts={Action.LEFT_HALF: DEFAULT_SHORTCUTS[Action.LEFT_HALF]})
        config_store = FakeConfigStore()
        hotkeys = object()

        def apply_settings(self, settings):
            applied.append(settings)
            self.settings = settings

        def rebind_hotkeys(self):
            return 0

    controller = preferences.PreferencesController(
        ctx=FakeCtx(),
        window=object(),
        shortcut_widgets={Action.LEFT_HALF: FakeShortcutWidget()},
    )

    assert controller.apply() is True
    assert saved[0].shortcuts[Action.LEFT_HALF] == ""
    assert applied[0].shortcuts[Action.LEFT_HALF] == ""
