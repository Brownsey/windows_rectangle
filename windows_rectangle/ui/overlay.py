"""Snap-preview overlay (brief §2 #13 / §3).

Frameless, translucent, topmost, click-through, no-activate Qt widget.
The drag-to-edge mouse hook calls `show_for(rect)` while the cursor is
inside a snap zone; on drop the overlay is hidden and the dispatcher
applies the action.

Click-through is achieved via Qt's `WA_TransparentForMouseEvents`. On
Win32 we also explicitly OR in `WS_EX_NOACTIVATE | WS_EX_TRANSPARENT`
after the window handle exists, defending against Qt versions that
forget one of those flags for a transient utility window.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..core.geometry import Rect

if TYPE_CHECKING:
    pass


_log = logging.getLogger(__name__)

# Win32 GWL_EXSTYLE additions we want guaranteed.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080


@dataclass(slots=True)
class OverlayController:
    """Holds the QWidget reference; required so Qt's parent-tracking
    doesn't garbage-collect the overlay between calls."""

    widget: object | None = None


def install() -> OverlayController:
    """Construct (but don't show) the overlay widget.

    Returns an `OverlayController`; call `show_for(controller, rect)` to
    place the preview and `hide(controller)` to drop it.
    """
    from PySide6 import QtCore, QtGui, QtWidgets

    flags = (
        QtCore.Qt.FramelessWindowHint
        | QtCore.Qt.WindowStaysOnTopHint
        | QtCore.Qt.Tool
        | QtCore.Qt.WindowDoesNotAcceptFocus
        | QtCore.Qt.WindowTransparentForInput
        | QtCore.Qt.BypassWindowManagerHint
    )

    w = QtWidgets.QWidget(None, flags)
    w.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
    w.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
    w.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
    w.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)

    # Paint: tinted translucent fill + a thin border, matching Rectangle's look.
    def paint_event(event):
        painter = QtGui.QPainter(w)
        try:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            fill = QtGui.QColor(30, 144, 255, 90)    # DodgerBlue @ ~35%
            border = QtGui.QColor(30, 144, 255, 220)
            r = w.rect().adjusted(1, 1, -1, -1)
            painter.fillRect(r, fill)
            pen = QtGui.QPen(border, 2)
            painter.setPen(pen)
            painter.drawRoundedRect(r, 6, 6)
        finally:
            painter.end()

    w.paintEvent = paint_event  # type: ignore[assignment]
    return OverlayController(widget=w)


def show_for(controller: OverlayController, rect: Rect) -> None:
    """Position the overlay at `rect` (physical pixels) and show it."""
    w = controller.widget
    if w is None:
        return
    w.setGeometry(rect.x, rect.y, rect.width, rect.height)
    w.show()
    _ensure_win32_exstyle(w)


def hide(controller: OverlayController) -> None:
    if controller.widget is not None:
        controller.widget.hide()


def _ensure_win32_exstyle(widget) -> None:
    """OR in WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW.

    Qt usually sets these via the flags above, but versions disagree.
    A redundant SetWindowLong is cheap and guarantees the contract.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        if hwnd == 0:
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        cur = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        want = cur | _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW
        if cur != want:
            user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, want)
    except Exception:  # noqa: BLE001
        _log.debug("could not adjust overlay ex-style", exc_info=True)
