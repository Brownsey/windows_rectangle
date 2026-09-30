"""Tests for windows_rectangle.adapters.win_dpi.

The real ctypes calls require Windows; on non-Windows we only verify
that the function returns DpiAwareness.NONE without raising.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from windows_rectangle.adapters.win_dpi import DpiAwareness, enable_dpi_awareness


def test_dpi_awareness_enum_members():
    # Stable string values — used in logs/config.
    assert DpiAwareness.PER_MONITOR_V2.value == "per_monitor_v2"
    assert DpiAwareness.PER_MONITOR.value == "per_monitor"
    assert DpiAwareness.SYSTEM.value == "system"
    assert DpiAwareness.NONE.value == "none"


def test_enable_on_non_windows_returns_none():
    if sys.platform == "win32":
        # On real Windows we expect a non-NONE level. Test the happy path.
        level = enable_dpi_awareness()
        assert level is not DpiAwareness.NONE
    else:
        assert enable_dpi_awareness() is DpiAwareness.NONE


def test_enable_does_not_raise():
    # Whatever the platform, this must not raise.
    enable_dpi_awareness()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPI API")
def test_fresh_process_enables_per_monitor_v2():
    if sys.getwindowsversion().build < 15063:
        pytest.skip("Per-Monitor V2 requires Windows 10 version 1703")
    app_root = Path(__file__).parents[1]
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(app_root)!r}); "
        "from windows_rectangle.adapters.win_dpi import enable_dpi_awareness; "
        "print(enable_dpi_awareness().value)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "per_monitor_v2"
