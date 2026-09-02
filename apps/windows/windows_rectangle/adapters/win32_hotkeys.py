"""Hotkeys adapter — Win32 RegisterHotKey on a dedicated pump thread.

Implements `ports.hotkeys.Hotkeys`. RegisterHotKey requires the same
thread that processes the WM_HOTKEY messages; this adapter spins one
daemon thread that runs a GetMessage loop and accepts commands via
a queue + PostThreadMessageW wakeup (brief §5 #6, #8).

Callbacks fire on the pump thread. The convention from the brief is
that callbacks marshal back to the main loop via `core.actionbus`.
This adapter just delivers — what the callback does is up to the
composition root.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading

from ..core.keymap import UnsupportedKeyError, translate
from ..core.shortcuts import ShortcutParseError, parse
from ..ports.hotkeys import HotkeyCallback, HotkeyRegistrationError

_log = logging.getLogger(__name__)


# Win32 message constants.
_WM_HOTKEY = 0x0312
_WM_APP = 0x8000
_WM_APP_WAKE = _WM_APP + 1


class Win32Hotkeys:
    """Run a dedicated daemon thread that owns the hotkey message pump."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32Hotkeys requires Windows")

        self._commands: queue.Queue = queue.Queue()
        self._callbacks: dict[int, HotkeyCallback] = {}
        self._next_id = 1
        self._thread_id: int | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._run_pump, name="WindowsRectangle-Hotkeys", daemon=True
        )
        self._thread.start()
        # Block until the pump thread has stored its tid.
        if not self._started.wait(timeout=5.0):
            raise RuntimeError("hotkey pump thread failed to start")

    # ----- Hotkeys protocol -----------------------------------------

    def register(self, combo: str, callback: HotkeyCallback) -> int:
        """Parse `combo`, hand it off to the pump thread, block for the result.

        Raises `HotkeyRegistrationError` if the combo is unparseable, has
        no Win32 mapping, or RegisterHotKey itself returns failure.
        """
        try:
            mod_mask, vk = translate(parse(combo))
        except (ShortcutParseError, UnsupportedKeyError) as e:
            raise HotkeyRegistrationError(f"bad combo {combo!r}: {e}") from e

        ack: queue.Queue = queue.Queue(maxsize=1)
        hotkey_id = self._next_id
        self._next_id += 1
        self._commands.put(("register", hotkey_id, mod_mask, vk, callback, ack))
        self._wake_pump()
        ok, err = ack.get(timeout=5.0)
        if not ok:
            raise HotkeyRegistrationError(f"RegisterHotKey failed for {combo!r}: err={err}")
        return hotkey_id

    def unregister(self, hotkey_id: int) -> None:
        ack: queue.Queue = queue.Queue(maxsize=1)
        self._commands.put(("unregister", hotkey_id, ack))
        self._wake_pump()
        ack.get(timeout=5.0)

    def unregister_all(self) -> None:
        for hid in list(self._callbacks.keys()):
            try:
                self.unregister(hid)
            except Exception:  # noqa: BLE001
                _log.warning("unregister_all: failed to unregister %s", hid, exc_info=True)

    def shutdown(self) -> None:
        """Stop the pump thread and release every registered hotkey."""
        self.unregister_all()
        self._commands.put(("quit",))
        self._wake_pump()
        self._thread.join(timeout=2.0)

    # ----- pump-thread internals ------------------------------------

    def _wake_pump(self) -> None:
        if self._thread_id is None:
            return
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostThreadMessageW(self._thread_id, _WM_APP_WAKE, 0, 0)

    def _run_pump(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        # Force creation of a message queue for this thread by calling
        # PeekMessage; otherwise PostThreadMessage may race the queue creation.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)

        self._thread_id = kernel32.GetCurrentThreadId()
        self._started.set()

        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret == 0 or ret == -1:  # WM_QUIT or error
                break

            if msg.message == _WM_HOTKEY:
                cb = self._callbacks.get(int(msg.wParam))
                if cb is not None:
                    try:
                        cb()
                    except Exception:  # noqa: BLE001
                        _log.exception("hotkey callback raised")
            elif msg.message == _WM_APP_WAKE:
                self._drain_commands(user32)
                if self._stopped.is_set():
                    break

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Final cleanup on thread exit — best effort.
        for hid in list(self._callbacks.keys()):
            user32.UnregisterHotKey(0, hid)
        self._callbacks.clear()

    def _drain_commands(self, user32) -> None:
        import ctypes

        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                return
            kind = cmd[0]
            if kind == "register":
                _, hid, mod_mask, vk, cb, ack = cmd
                ok = user32.RegisterHotKey(0, hid, mod_mask, vk)
                if ok:
                    self._callbacks[hid] = cb
                    ack.put((True, 0))
                else:
                    err = ctypes.get_last_error()
                    ack.put((False, err))
            elif kind == "unregister":
                _, hid, ack = cmd
                user32.UnregisterHotKey(0, hid)
                self._callbacks.pop(hid, None)
                ack.put((True, 0))
            elif kind == "quit":
                self._stopped.set()
                return
