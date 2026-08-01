"""Tests for windows_rectangle.__main__."""

import sys
from types import SimpleNamespace

import pytest
from windows_rectangle.__main__ import (
    _default_autostart_command_line,
    _parse_args,
    _run_qt,
    _should_open_preferences,
)


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.headless is False
    assert args.open_preferences is False
    assert args.tray is False
    assert args.command_line is None
    assert args.log_level == "INFO"


def test_parse_args_headless_flag():
    args = _parse_args(["--headless"])
    assert args.headless is True


def test_parse_args_open_preferences_flag():
    args = _parse_args(["--open-preferences"])
    assert args.open_preferences is True


def test_parse_args_preferences_alias():
    args = _parse_args(["--preferences"])
    assert args.open_preferences is True


def test_parse_args_tray_flag():
    args = _parse_args(["--tray"])
    assert args.tray is True


def test_parse_args_rejects_preferences_in_headless_mode():
    with pytest.raises(SystemExit):
        _parse_args(["--headless", "--open-preferences"])


def test_parse_args_rejects_tray_in_headless_mode():
    with pytest.raises(SystemExit):
        _parse_args(["--headless", "--tray"])


def test_parse_args_rejects_tray_with_open_preferences():
    with pytest.raises(SystemExit):
        _parse_args(["--tray", "--open-preferences"])


def test_parse_args_command_line():
    args = _parse_args(["--command-line", r"C:\app.exe"])
    assert args.command_line == r"C:\app.exe"


def test_parse_args_log_level():
    args = _parse_args(["--log-level", "DEBUG"])
    assert args.log_level == "DEBUG"


def test_parse_args_invalid_log_level_rejected():
    with pytest.raises(SystemExit):
        _parse_args(["--log-level", "TRACE"])


def test_version_flag_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        _parse_args(["--version"])
    assert exc.value.code == 0


def test_default_autostart_command_line_runs_tray_only(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Python\python.exe")
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    command_line = _default_autostart_command_line()

    assert command_line == r'"C:\Program Files\Python\python.exe" -m windows_rectangle --tray'
    assert "--open-preferences" not in command_line


def test_default_autostart_command_line_uses_packaged_exe(monkeypatch):
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\Windows Rectangle\app.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert (
        _default_autostart_command_line() == r'"C:\Program Files\Windows Rectangle\app.exe" --tray'
    )


def test_packaged_exe_opens_preferences_by_default(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    args = _parse_args([])

    assert _should_open_preferences(args) is True


def test_packaged_exe_tray_flag_suppresses_preferences(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    args = _parse_args(["--tray"])

    assert _should_open_preferences(args) is False


def test_source_run_opens_preferences_only_when_requested(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert _should_open_preferences(_parse_args([])) is False
    assert _should_open_preferences(_parse_args(["--open-preferences"])) is True


def test_run_qt_opens_preferences_when_requested(monkeypatch):
    calls: list[str] = []
    menu_callback = None

    class FakeSignal:
        def connect(self, callback):
            calls.append("timer_connected")
            self.callback = callback

    class FakeTimer:
        def __init__(self):
            self.timeout = FakeSignal()

        def setTimerType(self, timer_type):
            calls.append(f"timer_type:{timer_type}")

        def setInterval(self, interval):
            calls.append(f"interval:{interval}")

        def start(self):
            calls.append("timer_started")

        def stop(self):
            calls.append("timer_stopped")

    class FakeApplication:
        created = None

        def __init__(self, argv):
            self.argv = argv
            self.quit_on_last_window_closed = True
            FakeApplication.created = self

        @staticmethod
        def instance():
            return None

        def setQuitOnLastWindowClosed(self, value):
            self.quit_on_last_window_closed = value

        def exec(self):
            calls.append("exec")
            return 17

    def install_tray(ctx, *, on_open_preferences=None):
        nonlocal menu_callback
        calls.append("tray")
        assert on_open_preferences is not None
        menu_callback = on_open_preferences
        return object()

    def show_preferences(ctx):
        calls.append("preferences")

    fake_qt_core = SimpleNamespace(QTimer=FakeTimer, Qt=SimpleNamespace(PreciseTimer="precise"))
    fake_qt_widgets = SimpleNamespace(QApplication=FakeApplication)
    monkeypatch.setitem(
        sys.modules,
        "PySide6",
        SimpleNamespace(QtCore=fake_qt_core, QtWidgets=fake_qt_widgets),
    )
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", fake_qt_core)
    monkeypatch.setitem(
        sys.modules,
        "PySide6.QtWidgets",
        fake_qt_widgets,
    )
    monkeypatch.setitem(
        sys.modules,
        "windows_rectangle.ui.tray",
        SimpleNamespace(install=install_tray),
    )
    monkeypatch.setitem(
        sys.modules,
        "windows_rectangle.ui.preferences",
        SimpleNamespace(show=show_preferences),
    )

    rc = _run_qt(SimpleNamespace(drain_actions=lambda: 0), open_preferences=True)

    assert rc == 17
    assert calls == [
        "tray",
        "preferences",
        "timer_type:precise",
        "interval:16",
        "timer_connected",
        "timer_started",
        "exec",
        "timer_stopped",
    ]
    assert FakeApplication.created is not None
    assert FakeApplication.created.quit_on_last_window_closed is False
    assert menu_callback is not None

    menu_callback()

    assert calls[-1] == "preferences"
