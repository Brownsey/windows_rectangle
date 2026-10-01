"""Tests for windows_rectangle.adapters.win32_hotkeys.

On Windows: smoke-tests of register/unregister round-trip using an
unlikely-to-conflict hotkey (Ctrl+Alt+Shift+F24). We do NOT verify the
callback fires from a real key press (that would require synthesising
input). We do verify shutdown cleans up.

On non-Windows: constructor raises.
"""

import sys
import threading
import time

import pytest

from windows_rectangle.adapters.win32_hotkeys import Win32Hotkeys
from windows_rectangle.ports.hotkeys import HotkeyRegistrationError


def _register_with_request_failure(monkeypatch, reason: int | str) -> str:
    hotkeys = object.__new__(Win32Hotkeys)
    hotkeys._stopped = threading.Event()
    hotkeys._next_id = 1
    monkeypatch.setattr(hotkeys, "_request", lambda _command, _ack: (False, reason))
    with pytest.raises(HotkeyRegistrationError) as error:
        hotkeys.register("ctrl+alt+c", lambda: None)
    return str(error.value)


def test_register_explains_windows_hotkey_already_registered(monkeypatch):
    message = _register_with_request_failure(monkeypatch, 1409)

    assert "ctrl+alt+c" in message
    assert "already in use by another application" in message
    assert "1409" in message


@pytest.mark.parametrize("reason", [87, "wake failed", "1409"])
def test_register_preserves_unknown_request_failure(monkeypatch, reason):
    message = _register_with_request_failure(monkeypatch, reason)

    assert f"err={reason}" in message
    assert "already in use" not in message


def test_construction_blocked_off_windows():
    if sys.platform == "win32":
        h = Win32Hotkeys()
        try:
            assert h._thread.is_alive()
        finally:
            h.shutdown()
    else:
        with pytest.raises(RuntimeError):
            Win32Hotkeys()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_register_and_unregister():
    h = Win32Hotkeys()
    try:
        hid = h.register("ctrl+alt+shift+f24", lambda: None)
        assert isinstance(hid, int)
        h.unregister(hid)
    finally:
        h.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_unregister_all_clears_state():
    h = Win32Hotkeys()
    try:
        h.register("ctrl+alt+shift+f23", lambda: None)
        h.register("ctrl+alt+shift+f24", lambda: None)
        h.unregister_all()
        assert h._callbacks == {}
    finally:
        h.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_register_bad_combo_raises():
    h = Win32Hotkeys()
    try:
        with pytest.raises(HotkeyRegistrationError):
            h.register("", lambda: None)
        with pytest.raises(HotkeyRegistrationError):
            h.register("ctrl+alt+nosuchkey", lambda: None)
    finally:
        h.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_shutdown_stops_thread():
    h = Win32Hotkeys()
    h.register("ctrl+alt+shift+f22", lambda: None)
    h.shutdown()
    # Give the thread a moment to wind down.
    time.sleep(0.1)
    assert not h._thread.is_alive()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_pump_startup_failure_raises_from_constructor(monkeypatch):
    def fail_start(_self):
        raise OSError("pump failed")

    monkeypatch.setattr(Win32Hotkeys, "_run_pump", fail_start)
    with pytest.raises(RuntimeError, match="pump failed"):
        Win32Hotkeys()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_register_after_shutdown_fails_immediately():
    h = Win32Hotkeys()
    h.shutdown()
    with pytest.raises(HotkeyRegistrationError, match="stopped"):
        h.register("ctrl+alt+shift+f24", lambda: None)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_failed_wakeup_cannot_register_later(monkeypatch):
    h = Win32Hotkeys()
    real_wake = h._wake_pump
    try:
        monkeypatch.setattr(h, "_wake_pump", lambda: False)
        with pytest.raises(HotkeyRegistrationError, match="wake"):
            h.register("ctrl+alt+shift+f22", lambda: None)
        monkeypatch.setattr(h, "_wake_pump", real_wake)
        live_id = h.register("ctrl+alt+shift+f23", lambda: None)
        assert set(h._callbacks) == {live_id}
    finally:
        monkeypatch.setattr(h, "_wake_pump", real_wake)
        h.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_unregister_after_shutdown_fails_immediately():
    h = Win32Hotkeys()
    hotkey_id = h.register("ctrl+alt+shift+f24", lambda: None)
    h.shutdown()
    with pytest.raises(RuntimeError, match="stopped"):
        h.unregister(hotkey_id)
