"""WindowManager adapter — Win32 / ctypes implementation.

Implements `ports.window_manager.WindowManager` against user32 + dwmapi +
shcore. No pywin32 dependency; everything is via stdlib `ctypes`.

The module-level imports are deliberately stdlib-only so the module can
be *imported* on non-Windows (for IDE indexing, code review, and CI
running the core test suite). Instantiation of `Win32WindowManager` is
guarded with a runtime platform check.

Translates between the OS rect (outer, includes the ~7px invisible
border — brief §5 #2) and our internal visible rect using
`core.borders.measure / to_outer_rect / to_visible_rect`.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from ..core.borders import BorderInsets, measure, to_outer_rect, to_visible_rect
from ..core.eligibility import WindowFlags
from ..core.geometry import Rect
from ..ports.window_manager import MonitorInfo, WindowHandle

if TYPE_CHECKING:
    import ctypes
    from ctypes import wintypes


_log = logging.getLogger(__name__)


# --- Win32 constants ---
_GWL_STYLE = -16
_GWL_EXSTYLE = -20

_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_DISABLED = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080

_SW_RESTORE = 9
_SW_SHOWMAXIMIZED = 3

_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_DWMWA_CLOAKED = 14

_MONITORINFOF_PRIMARY = 0x00000001
_MONITOR_DEFAULTTONEAREST = 0x00000002

# SetWindowPos flags
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_ASYNCWINDOWPOS = 0x4000


class Win32WindowManager:
    """Real WindowManager adapter. Construct inside `bind_win32(...)` only."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Win32WindowManager requires Windows")
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes

        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._dwm = ctypes.WinDLL("dwmapi", use_last_error=True)

        # Signatures we care about (typed for safety where it matters).
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.IsWindow.argtypes = [wintypes.HWND]
        self._user32.IsWindow.restype = wintypes.BOOL
        self._user32.IsIconic.argtypes = [wintypes.HWND]
        self._user32.IsIconic.restype = wintypes.BOOL
        self._user32.GetShellWindow.restype = wintypes.HWND
        self._user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.GetWindowLongW.restype = ctypes.c_long
        self._user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]
        self._user32.SetWindowPos.restype = wintypes.BOOL
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL

    # ----- helpers ---------------------------------------------------

    def _hwnd(self, handle: WindowHandle) -> int:
        # Our port lets handle be any Hashable; in practice it's int(HWND).
        return int(handle)  # type: ignore[arg-type]

    def _outer_rect(self, handle: WindowHandle) -> Rect:
        ct = self._ct
        wt = self._wt
        r = wt.RECT()
        if not self._user32.GetWindowRect(self._hwnd(handle), ct.byref(r)):
            raise OSError(f"GetWindowRect failed: {ct.get_last_error()}")
        return Rect.from_ltrb(r.left, r.top, r.right, r.bottom)

    def _extended_frame(self, handle: WindowHandle) -> Rect | None:
        ct = self._ct
        wt = self._wt
        r = wt.RECT()
        hr = self._dwm.DwmGetWindowAttribute(
            self._hwnd(handle),
            _DWMWA_EXTENDED_FRAME_BOUNDS,
            ct.byref(r),
            ct.sizeof(r),
        )
        if hr != 0:
            return None
        return Rect.from_ltrb(r.left, r.top, r.right, r.bottom)

    def _insets(self, handle: WindowHandle) -> BorderInsets:
        outer = self._outer_rect(handle)
        ext = self._extended_frame(handle)
        if ext is None:
            return BorderInsets()
        return measure(outer, ext)

    # ----- WindowManager protocol -----------------------------------

    def get_active_window(self) -> WindowHandle | None:
        h = self._user32.GetForegroundWindow()
        if not h:
            return None
        if h == self._user32.GetShellWindow():
            return None
        return int(h)

    def get_window_rect(self, handle: WindowHandle) -> Rect:
        """Return the *visible* rect — we hide the invisible border from core."""
        outer = self._outer_rect(handle)
        return to_visible_rect(outer, self._insets(handle))

    def set_window_rect(self, handle: WindowHandle, rect: Rect) -> bool:
        # Expand the visible rect we were handed into the outer rect Win32 expects.
        outer = to_outer_rect(rect, self._insets(handle))
        flags = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_ASYNCWINDOWPOS
        ok = self._user32.SetWindowPos(
            self._hwnd(handle), 0,
            outer.x, outer.y, outer.width, outer.height,
            flags,
        )
        if not ok:
            err = self._ct.get_last_error()
            _log.info("SetWindowPos failed hwnd=%s err=%s", handle, err)
        return bool(ok)

    def is_window_valid(self, handle: WindowHandle) -> bool:
        return bool(self._user32.IsWindow(self._hwnd(handle)))

    def get_window_flags(self, handle: WindowHandle) -> WindowFlags:
        ct = self._ct
        wt = self._wt
        h = self._hwnd(handle)
        style = self._user32.GetWindowLongW(h, _GWL_STYLE)
        ex_style = self._user32.GetWindowLongW(h, _GWL_EXSTYLE)

        # DWMWA_CLOAKED returns a DWORD; nonzero -> cloaked (UWP/Store apps
        # that aren't actually visible despite being in the z-order).
        cloaked = wt.DWORD(0)
        cloaked_hr = self._dwm.DwmGetWindowAttribute(
            h, _DWMWA_CLOAKED, ct.byref(cloaked), ct.sizeof(cloaked)
        )
        is_cloaked = (cloaked_hr == 0) and (cloaked.value != 0)
        return WindowFlags(
            has_caption=bool(style & _WS_CAPTION),
            has_thick_frame=bool(style & _WS_THICKFRAME),
            is_tool_window=bool(ex_style & _WS_EX_TOOLWINDOW),
            is_shell_window=(h == int(self._user32.GetShellWindow())),
            is_cloaked=is_cloaked,
            is_minimized=bool(self._user32.IsIconic(h)),
            is_disabled=bool(style & _WS_DISABLED),
        )

    def is_maximized(self, handle: WindowHandle) -> bool:
        ct = self._ct
        wt = self._wt
        wp = _WINDOWPLACEMENT(ct, wt)
        wp.length = ct.sizeof(wp)
        if not self._user32.GetWindowPlacement(self._hwnd(handle), ct.byref(wp)):
            return False
        return wp.showCmd == _SW_SHOWMAXIMIZED

    def restore_window(self, handle: WindowHandle) -> None:
        self._user32.ShowWindow(self._hwnd(handle), _SW_RESTORE)

    def list_monitors(self) -> list[MonitorInfo]:
        ct = self._ct
        wt = self._wt
        monitors: list[MonitorInfo] = []

        # EnumDisplayMonitors callback prototype:
        # BOOL CALLBACK(HMONITOR, HDC, LPRECT, LPARAM)
        MonitorEnumProc = ct.WINFUNCTYPE(
            wt.BOOL, wt.HMONITOR, wt.HDC, ct.POINTER(wt.RECT), wt.LPARAM
        )

        def callback(hmon, hdc, lprect, lparam):
            info = _MONITORINFO(ct, wt)
            info.cbSize = ct.sizeof(info)
            if not self._user32.GetMonitorInfoW(hmon, ct.byref(info)):
                return True
            mb = info.rcMonitor
            wb = info.rcWork
            monitors.append(MonitorInfo(
                handle=int(hmon),
                bounds=Rect.from_ltrb(mb.left, mb.top, mb.right, mb.bottom),
                work_area=Rect.from_ltrb(wb.left, wb.top, wb.right, wb.bottom),
                is_primary=bool(info.dwFlags & _MONITORINFOF_PRIMARY),
            ))
            return True

        self._user32.EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
        return monitors

    def monitor_for_window(self, handle: WindowHandle) -> MonitorInfo | None:
        ct = self._ct
        wt = self._wt
        hmon = self._user32.MonitorFromWindow(
            self._hwnd(handle), _MONITOR_DEFAULTTONEAREST
        )
        if not hmon:
            return None
        info = _MONITORINFO(ct, wt)
        info.cbSize = ct.sizeof(info)
        if not self._user32.GetMonitorInfoW(hmon, ct.byref(info)):
            return None
        mb = info.rcMonitor
        wb = info.rcWork
        return MonitorInfo(
            handle=int(hmon),
            bounds=Rect.from_ltrb(mb.left, mb.top, mb.right, mb.bottom),
            work_area=Rect.from_ltrb(wb.left, wb.top, wb.right, wb.bottom),
            is_primary=bool(info.dwFlags & _MONITORINFOF_PRIMARY),
        )


# --- ctypes Structure builders (factories — avoid import-time ctypes use) ---


def _MONITORINFO(ct, wt):
    """Returns a `MONITORINFO` Structure class for the given ctypes/wintypes."""
    class MONITORINFO(ct.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("rcMonitor", wt.RECT),
            ("rcWork", wt.RECT),
            ("dwFlags", wt.DWORD),
        ]
    return MONITORINFO()


def _WINDOWPLACEMENT(ct, wt):
    class WINDOWPLACEMENT(ct.Structure):
        _fields_ = [
            ("length", wt.UINT),
            ("flags", wt.UINT),
            ("showCmd", wt.UINT),
            ("ptMinPosition", wt.POINT),
            ("ptMaxPosition", wt.POINT),
            ("rcNormalPosition", wt.RECT),
        ]
    return WINDOWPLACEMENT()
