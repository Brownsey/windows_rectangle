"""Tests for windows_rectangle.adapters.win32_hotkeys.

On Windows: smoke-tests of register/unregister round-trip using an
unlikely-to-conflict hotkey (Ctrl+Alt+Shift+F24). We do NOT verify the
callback fires from a real key press (that would require synthesising
input). We do verify shutdown cleans up.

On non-Windows: constructor raises.
"""

import sys
import time

import pytest

from windows_rectangle.adapters.win32_hotkeys import Win32Hotkeys
from windows_rectangle.ports.hotkeys import HotkeyRegistrationError


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
