"""Tests for windows_rectangle.adapters.win32_windows.

Non-Windows: only verify the module imports + non-Windows construction raises.
Windows: smoke-test read-only operations against the current foreground HWND.
The tests never *move* a window — that would interfere with the user's desktop.
"""

import sys

import pytest
from windows_rectangle.adapters.win32_windows import Win32WindowManager


def test_module_imports_on_any_platform():
    # Just by reaching here, the module imported fine on non-Windows too.
    assert Win32WindowManager is not None


def test_construction_blocked_off_windows():
    if sys.platform == "win32":
        # Construction must succeed on real Windows.
        wm = Win32WindowManager()
        assert wm is not None
    else:
        with pytest.raises(RuntimeError):
            Win32WindowManager()


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_list_monitors_on_windows_returns_at_least_one():
    wm = Win32WindowManager()
    mons = wm.list_monitors()
    assert len(mons) >= 1
    # Each monitor should expose a non-empty work area.
    for m in mons:
        assert m.work_area.width > 0
        assert m.work_area.height > 0
        # rcWork is a subset of rcMonitor (taskbar excluded).
        assert m.work_area.left >= m.bounds.left
        assert m.work_area.right <= m.bounds.right


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_get_active_window_returns_int_or_none():
    wm = Win32WindowManager()
    h = wm.get_active_window()
    assert h is None or isinstance(h, int)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_window_flags_for_active_window_are_sane():
    wm = Win32WindowManager()
    h = wm.get_active_window()
    if h is None:
        pytest.skip("no active window")
    flags = wm.get_window_flags(h)
    # Whatever it is, the boolean fields should be bools, not None.
    assert isinstance(flags.has_caption, bool)
    assert isinstance(flags.has_thick_frame, bool)
