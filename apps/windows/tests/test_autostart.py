"""Tests for windows_rectangle.adapters.winreg_autostart.

Only `MemoryAutoStart` and the helpers are tested here — the real
winreg adapter requires Windows + would mutate the actual user
registry, which we don't do in unit tests.
"""

import pytest
from windows_rectangle.adapters.winreg_autostart import (
    MemoryAutoStart,
    best_available,
)
from windows_rectangle.ports.autostart import APP_ID, RUN_KEY_PATH


def test_app_id_and_path_constants():
    assert APP_ID == "WindowsRectangle"
    assert RUN_KEY_PATH.endswith(r"CurrentVersion\Run")


def test_memory_starts_disabled():
    a = MemoryAutoStart()
    assert not a.is_enabled()
    assert a.command_line is None


def test_memory_enable_and_disable():
    a = MemoryAutoStart()
    a.enable(r"C:\Apps\windows_rectangle.exe")
    assert a.is_enabled()
    assert a.command_line == r"C:\Apps\windows_rectangle.exe"
    a.disable()
    assert not a.is_enabled()
    assert a.command_line is None


def test_memory_enable_rejects_empty():
    a = MemoryAutoStart()
    with pytest.raises(ValueError):
        a.enable("")


def test_memory_disable_when_already_disabled_is_noop():
    a = MemoryAutoStart()
    a.disable()
    a.disable()
    assert not a.is_enabled()


def test_memory_enable_overwrites_previous():
    a = MemoryAutoStart()
    a.enable(r"C:\old.exe")
    a.enable(r"C:\new.exe")
    assert a.command_line == r"C:\new.exe"


def test_best_available_returns_something():
    impl = best_available()
    # On non-Windows CI it's MemoryAutoStart; on Windows it's WinregAutoStart.
    # We don't care which — just that it satisfies the protocol.
    assert hasattr(impl, "is_enabled")
    assert hasattr(impl, "enable")
    assert hasattr(impl, "disable")
