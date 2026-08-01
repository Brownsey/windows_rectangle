"""Port: window + monitor enumeration and movement.

Adapters (Windows-specific) implement this; `core/` calls only this.
Tests provide an in-memory fake.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Protocol

from ..core.eligibility import WindowFlags
from ..core.geometry import Rect

# A handle that uniquely identifies a window. On Windows this is the HWND
# (int); we keep it `Hashable` so tests/fakes can use anything.
WindowHandle = Hashable


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    """One physical display.

    `work_area` excludes the taskbar (Windows `rcWork`).
    `bounds` is the full monitor rect (`rcMonitor`).
    `is_primary` matches `MONITORINFOF_PRIMARY`.
    """

    handle: Hashable
    bounds: Rect
    work_area: Rect
    is_primary: bool = False


class WindowManager(Protocol):
    """Operations the dispatcher needs from the OS."""

    def get_active_window(self) -> WindowHandle | None:
        """The frontmost eligible window, or None if nothing usable."""

    def get_window_rect(self, handle: WindowHandle) -> Rect:
        """Current outer rect of the window in physical pixels.

        Adapters should already have corrected for the Windows 10/11
        invisible drop-shadow border (brief §5.2).
        """

    def set_window_rect(self, handle: WindowHandle, rect: Rect) -> bool:
        """Move/resize the window. Returns False on failure (e.g. UIPI block)."""

    def is_window_valid(self, handle: WindowHandle) -> bool:
        """`IsWindow(hwnd)` — used to prune cycle/history state."""

    def get_window_flags(self, handle: WindowHandle) -> WindowFlags:
        """Style/state flags used by `core.eligibility.classify` to decide
        whether the window may be moved, resized, both, or skipped (brief §5 #10).
        """

    def is_maximized(self, handle: WindowHandle) -> bool:
        """True if the window is in a maximized or OS-snapped state.

        SetWindowPos misbehaves on maximized windows (brief §5 #4); the
        dispatcher restores first.
        """

    def restore_window(self, handle: WindowHandle) -> None:
        """`ShowWindow(SW_RESTORE)` — used before moving a maximized window."""

    def list_monitors(self) -> list[MonitorInfo]:
        """All monitors, in a stable order — used for next/prev display."""

    def monitor_for_window(self, handle: WindowHandle) -> MonitorInfo | None:
        """Monitor that currently contains (most of) the window."""
