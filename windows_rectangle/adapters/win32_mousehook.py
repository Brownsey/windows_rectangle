"""Low-level mouse hook adapter (brief §5 #7, brief §2 #13).

Wraps `SetWindowsHookExW(WH_MOUSE_LL)` and the dedicated message-pump
thread it requires. The hook callback runs in-process; Windows times
the hook out if it doesn't return fast, so this adapter's contract is:
the consumer's `on_event(kind, x, y)` callback must be O(1).

Typical wiring (production):
    hook = Win32MouseHook(on_event=lambda kind, x, y: handle(ctx, kind, x, y))
    # `handle` only LatestValue.set((x,y)) on "move" and ActionBus.submit on "up".

Shutdown unhooks the global hook — important; a leaked WH_MOUSE_LL
degrades the whole OS (brief §5 #11).
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable


_log = logging.getLogger(__name__)


# Win32 message + hook constants.
_WH_MOUSE_LL = 14
_WM_QUIT = 0x0012

_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP = 0x0202
_WM_RBUTTONDOWN = 0x0204
_WM_RBUTTONUP = 0x0205
_WM_MBUTTONDOWN = 0x0207
_WM_MBUTTONUP = 0x0208


# Event kind strings handed to the consumer.
EVENT_MOVE = "move"
EVENT_LBUTTON_DOWN = "lbutton_down"
EVENT_LBUTTON_UP = "lbutton_up"
EVENT_RBUTTON_DOWN = "rbutton_down"
EVENT_RBUTTON_UP = "rbutton_up"
EVENT_MBUTTON_DOWN = "mbutton_down"
EVENT_MBUTTON_UP = "mbutton_up"


_WPARAM_TO_KIND = {
    _WM_MOUSEMOVE: EVENT_MOVE,
    _WM_LBUTTONDOWN: EVENT_LBUTTON_DOWN,
    _WM_LBUTTONUP: EVENT_LBUTTON_UP,
    _WM_RBUTTONDOWN: EVENT_RBUTTON_DOWN,
    _WM_RBUTTONUP: EVENT_RBUTTON_UP,
    _WM_MBUTTONDOWN: EVENT_MBUTTON_DOWN,
    _WM_MBUTTONUP: EVENT_MBUTTON_UP,
}


MouseEventCallback = Callable[[str, int, int], None]


class Win32MouseHook:
    """Owns a daemon thread that installs WH_MOUSE_LL and pumps messages.

    `on_event(kind, x, y)` fires on the hook thread and MUST return fast.
    """

    def __init__(self, on_event: MouseEventCallback) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32MouseHook requires Windows")
        self._on_event = on_event
        self._thread_id: int | None = None
        self._started = threading.Event()
        self._stopped = threading.Event()
        # The HOOKPROC must outlive the hook installation; keep a ref.
        self._hook_proc = None
        self._hook_handle: int = 0
        self._thread = threading.Thread(
            target=self._run, name="WindowsRectangle-MouseHook", daemon=True
        )
        self._thread.start()
        if not self._started.wait(timeout=5.0):
            raise RuntimeError("mouse hook thread failed to start")

    def shutdown(self) -> None:
        """Unhook + stop the pump. Idempotent."""
        if self._stopped.is_set():
            return
        self._stopped.set()
        if self._thread_id is not None:
            import ctypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)

    # ----- internals ------------------------------------------------

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        # Declare 64-bit-safe argtypes/restype so HMODULE / HHOOK aren't
        # truncated to int on x64 (caused error 126 / ERROR_MOD_NOT_FOUND).
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        # MSLLHOOKSTRUCT layout — only `pt` is needed here.
        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        # HOOKPROC signature: LRESULT (int nCode, WPARAM wParam, LPARAM lParam)
        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        # CallNextHookEx setup.
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.CallNextHookEx.restype = ctypes.c_long
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p

        def hook_proc(nCode, wParam, lParam):
            if nCode == 0:  # HC_ACTION
                try:
                    info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT))[0]
                    kind = _WPARAM_TO_KIND.get(int(wParam))
                    if kind is not None:
                        try:
                            self._on_event(kind, info.pt.x, info.pt.y)
                        except Exception:  # noqa: BLE001
                            _log.exception("mouse hook consumer raised")
                except Exception:  # noqa: BLE001
                    _log.debug("mouse hook proc raised", exc_info=True)
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # Keep a strong ref to the HOOKPROC instance — must outlive the install.
        self._hook_proc = HOOKPROC(hook_proc)
        # Force message-queue creation before SetWindowsHookEx is checked by the OS.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 0)

        self._thread_id = kernel32.GetCurrentThreadId()
        h_module = kernel32.GetModuleHandleW(None)
        handle = user32.SetWindowsHookExW(_WH_MOUSE_LL, self._hook_proc, h_module, 0)
        if not handle:
            _log.error("SetWindowsHookExW failed: err=%s", ctypes.get_last_error())
            self._started.set()  # unblock constructor — will see stopped
            self._stopped.set()
            return
        self._hook_handle = handle
        self._started.set()

        # Pump messages until WM_QUIT.
        while not self._stopped.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret == 0 or ret == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = 0
