"""Per-monitor DPI awareness (brief §5 #1).

Declares the process *Per-Monitor-V2 DPI aware* at startup. Mixed-DPI
multi-monitor setups otherwise hand us scaled (logical) coordinates,
which makes window-geometry math drift by the scale factor on the
non-primary monitor.

Strategy is a fallback chain — newer APIs preferred, but we still come
up correct on Windows 7/8.1 where Per-Monitor V2 isn't available.
Must be called exactly once, before any HWND is created.
"""

from __future__ import annotations

import logging
import sys
from enum import StrEnum

_log = logging.getLogger(__name__)


# DPI_AWARENESS_CONTEXT values (winuser.h). The handle values are negative
# integers cast to HANDLE; passing them as ints to ctypes works because
# SetProcessDpiAwarenessContext takes a DPI_AWARENESS_CONTEXT (a void*).
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4  # Win10 1703+
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3  # Win10 +

# PROCESS_DPI_AWARENESS values (shcore.h).
_PROCESS_PER_MONITOR_DPI_AWARE = 2
_PROCESS_SYSTEM_DPI_AWARE = 1


class DpiAwareness(StrEnum):
    """The level of awareness actually achieved."""

    PER_MONITOR_V2 = "per_monitor_v2"
    PER_MONITOR = "per_monitor"
    SYSTEM = "system"
    NONE = "none"


def enable_dpi_awareness() -> DpiAwareness:
    """Try the best-available DPI mode. Returns the level actually set.

    On non-Windows / older runtimes that lack every API, returns
    `DpiAwareness.NONE` rather than raising — calling code should still
    proceed (geometry will be off but app stays usable).
    """
    if sys.platform != "win32":
        return DpiAwareness.NONE

    import ctypes

    # 1. user32.SetProcessDpiAwarenessContext(-4)
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if user32.SetProcessDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return DpiAwareness.PER_MONITOR_V2
        if user32.SetProcessDpiAwarenessContext(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE):
            return DpiAwareness.PER_MONITOR
    except (AttributeError, OSError):
        # SetProcessDpiAwarenessContext absent → Win 8.1 or earlier.
        pass

    # 2. shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE) — Win 8.1+
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        if shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE) == 0:
            return DpiAwareness.PER_MONITOR
        if shcore.SetProcessDpiAwareness(_PROCESS_SYSTEM_DPI_AWARE) == 0:
            return DpiAwareness.SYSTEM
    except (AttributeError, OSError):
        pass

    # 3. user32.SetProcessDPIAware() — system-aware, Vista+. Last resort.
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if user32.SetProcessDPIAware():
            return DpiAwareness.SYSTEM
    except (AttributeError, OSError):
        pass

    _log.warning("could not set any DPI awareness level — falling back to NONE")
    return DpiAwareness.NONE
