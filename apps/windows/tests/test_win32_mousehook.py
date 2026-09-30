"""Tests for windows_rectangle.adapters.win32_mousehook.

Windows-only smoke tests: install + shutdown round-trip. We do not
synthesise mouse events (that would hijack the user's pointer); we
verify that the hook thread starts, the hook handle is non-zero, and
shutdown cleans up.

On non-Windows: constructor raises.
"""

import ctypes
import sys
import time

import pytest

from windows_rectangle.adapters.win32_mousehook import (
    EVENT_LBUTTON_DOWN,
    EVENT_MOVE,
    Win32MouseHook,
)


def test_construction_blocked_off_windows():
    if sys.platform == "win32":
        h = Win32MouseHook(on_event=lambda *a: None)
        try:
            assert h._thread.is_alive()
            # The hook handle should have been installed.
            assert h._hook_handle != 0
        finally:
            h.shutdown()
    else:
        with pytest.raises(RuntimeError):
            Win32MouseHook(on_event=lambda *a: None)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_shutdown_stops_thread():
    h = Win32MouseHook(on_event=lambda *a: None)
    h.shutdown()
    time.sleep(0.1)
    assert not h._thread.is_alive()
    assert h._hook_handle == 0


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_shutdown_idempotent():
    h = Win32MouseHook(on_event=lambda *a: None)
    h.shutdown()
    h.shutdown()  # second call must not raise


def test_event_kinds_are_distinct():
    # Sanity: the kind strings the consumer might pattern-match on
    # are stable + distinct.
    assert EVENT_MOVE != EVENT_LBUTTON_DOWN
    assert EVENT_MOVE == "move"
    assert EVENT_LBUTTON_DOWN == "lbutton_down"


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_install_failure_raises_from_constructor(monkeypatch):
    def fail_install(self):
        self._startup_error = OSError("hook install failed")
        self._stopped.set()
        self._started.set()

    monkeypatch.setattr(Win32MouseHook, "_run", fail_install)
    with pytest.raises(RuntimeError, match="hook install failed"):
        Win32MouseHook(on_event=lambda *a: None)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_hook_result_type_is_pointer_sized():
    hook = Win32MouseHook(on_event=lambda *a: None)
    try:
        assert ctypes.sizeof(hook._hook_proc._restype_) == ctypes.sizeof(ctypes.c_void_p)
    finally:
        hook.shutdown()
