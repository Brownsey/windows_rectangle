"""Port: window + monitor enumeration and movement.

Adapters (Windows-specific) implement this; `core/` calls only this.
Tests provide an in-memory fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Protocol

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

    def list_monitors(self) -> list[MonitorInfo]:
        """All monitors, in a stable order — used for next/prev display."""

    def monitor_for_window(self, handle: WindowHandle) -> MonitorInfo | None:
        """Monitor that currently contains (most of) the window."""
