"""Shared test fixtures, including an in-memory WindowManager fake."""

from __future__ import annotations

from dataclasses import dataclass, field

from windows_rectangle.core.eligibility import WindowFlags
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.monitors import best_monitor_for
from windows_rectangle.ports.window_manager import MonitorInfo, WindowHandle


@dataclass(slots=True)
class FakeWindowManager:
    """In-memory implementation of the WindowManager Protocol.

    Tests construct one with monitors + windows, then drive the dispatcher.
    """

    monitors: list[MonitorInfo] = field(default_factory=list)
    windows: dict[WindowHandle, Rect] = field(default_factory=dict)
    active: WindowHandle | None = None
    blocked: set[WindowHandle] = field(default_factory=set)
    blocked_topmost: set[WindowHandle] = field(default_factory=set)
    always_on_top: set[WindowHandle] = field(default_factory=set)
    maximized: set[WindowHandle] = field(default_factory=set)
    flags: dict[WindowHandle, WindowFlags] = field(default_factory=dict)
    default_flags: WindowFlags = field(
        default_factory=lambda: WindowFlags(has_caption=True, has_thick_frame=True)
    )
    move_log: list[tuple[WindowHandle, Rect]] = field(default_factory=list)
    restore_log: list[WindowHandle] = field(default_factory=list)

    # ----- WindowManager protocol -----

    def get_active_window(self) -> WindowHandle | None:
        return self.active

    def get_window_rect(self, handle: WindowHandle) -> Rect:
        return self.windows[handle]

    def set_window_rect(self, handle: WindowHandle, rect: Rect) -> bool:
        if handle in self.blocked:
            return False
        self.windows[handle] = rect
        self.move_log.append((handle, rect))
        return True

    def is_window_valid(self, handle: WindowHandle) -> bool:
        return handle in self.windows

    def get_window_flags(self, handle: WindowHandle) -> WindowFlags:
        return self.flags.get(handle, self.default_flags)

    def is_maximized(self, handle: WindowHandle) -> bool:
        return handle in self.maximized

    def restore_window(self, handle: WindowHandle) -> None:
        self.maximized.discard(handle)
        self.restore_log.append(handle)

    def is_always_on_top(self, handle: WindowHandle) -> bool:
        return handle in self.always_on_top

    def set_always_on_top(self, handle: WindowHandle, enabled: bool) -> bool:
        if handle in self.blocked_topmost:
            return False
        if enabled:
            self.always_on_top.add(handle)
        else:
            self.always_on_top.discard(handle)
        return True

    def list_monitors(self) -> list[MonitorInfo]:
        return list(self.monitors)

    def monitor_for_window(self, handle: WindowHandle) -> MonitorInfo | None:
        if handle not in self.windows:
            return None
        # Use the production utility so the fake's behaviour (incl. tie-break
        # ordering) matches what a real win32 adapter that falls back to
        # overlap-area would do.
        return best_monitor_for(self.windows[handle], self.monitors)


def make_monitor(
    handle: int, x: int, y: int, w: int, h: int, taskbar: int = 40, primary: bool = False
) -> MonitorInfo:
    """Build a MonitorInfo with a taskbar-sized strip removed from the bottom."""
    bounds = Rect(x, y, w, h)
    work = Rect(x, y, w, h - taskbar)
    return MonitorInfo(handle=handle, bounds=bounds, work_area=work, is_primary=primary)
