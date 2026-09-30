"""Tests for windows_rectangle.adapters.win32_windows.

Non-Windows: only verify the module imports + non-Windows construction raises.
Windows: smoke-test read-only operations against the current foreground HWND.
The tests never *move* a window — that would interfere with the user's desktop.
"""

import sys

import pytest

from windows_rectangle.adapters.win32_windows import Win32WindowManager
from windows_rectangle.core.geometry import Rect


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
def test_list_windows_returns_sane_identity_data():
    wm = Win32WindowManager()
    for window in wm.list_windows():
        assert isinstance(window.handle, int)
        assert window.title
        assert isinstance(window.process_name, str)


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


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_topmost_state_for_active_window_is_boolean():
    wm = Win32WindowManager()
    h = wm.get_active_window()
    if h is None:
        pytest.skip("no active window")
    assert isinstance(wm.is_always_on_top(h), bool)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_visible_rect_uses_dwm_frame_without_outer_query(monkeypatch):
    wm = Win32WindowManager()
    frame = Rect(10, 20, 300, 200)
    monkeypatch.setattr(wm, "_extended_frame", lambda _handle: frame)
    monkeypatch.setattr(wm, "_outer_rect", lambda _handle: pytest.fail("outer query"))
    assert wm.get_window_rect(123) == frame


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_visible_rect_falls_back_to_outer_when_dwm_unavailable(monkeypatch):
    wm = Win32WindowManager()
    monkeypatch.setattr(wm, "_extended_frame", lambda _handle: None)
    monkeypatch.setattr(wm, "_outer_rect", lambda _handle: Rect(10, 20, 300, 200))
    assert wm.get_window_rect(123) == Rect(10, 20, 300, 200)


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_drag_window_is_none_when_no_native_move_size(monkeypatch):
    wm = Win32WindowManager()

    def idle(_thread_id, info_ptr):
        info_ptr._obj.flags = 0
        info_ptr._obj.hwndMoveSize = 0x12345
        return True

    monkeypatch.setattr(wm._user32, "GetGUIThreadInfo", idle)
    assert wm.get_drag_window() is None


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_drag_window_reads_move_size_handle(monkeypatch):
    wm = Win32WindowManager()

    def moving(_thread_id, info_ptr):
        assert _thread_id == 0
        info_ptr._obj.flags = 0x0002
        info_ptr._obj.hwndMoveSize = 0x12345
        return True

    monkeypatch.setattr(wm._user32, "GetGUIThreadInfo", moving)
    assert wm.get_drag_window() == 0x12345


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_escape_pressed_uses_high_key_state_bit(monkeypatch):
    wm = Win32WindowManager()

    def pressed(key):
        assert key == 0x1B
        return -32768

    monkeypatch.setattr(wm._user32, "GetAsyncKeyState", pressed)
    assert wm.is_escape_pressed() is True
    monkeypatch.setattr(wm._user32, "GetAsyncKeyState", lambda _key: 1)
    assert wm.is_escape_pressed() is False


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_restore_posts_without_waiting_for_target_window(monkeypatch):
    wm = Win32WindowManager()
    posted = []
    monkeypatch.setattr(
        wm._user32, "ShowWindowAsync", lambda handle, cmd: posted.append((handle, cmd))
    )
    monkeypatch.setattr(wm._user32, "ShowWindow", lambda *_args: pytest.fail("synchronous show"))
    wm.restore_window(0x12345)
    assert posted == [(0x12345, 9)]


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("accepted", [True, False])
def test_topmost_posts_without_moving_resizing_or_activating(monkeypatch, enabled, accepted):
    wm = Win32WindowManager()
    requests = []

    def position(*args):
        requests.append(args)
        return accepted

    monkeypatch.setattr(wm._user32, "SetWindowPos", position)
    assert wm.set_always_on_top(0x12345, enabled) is accepted
    handle, insert_after, x, y, width, height, flags = requests[0]
    assert handle == 0x12345
    assert insert_after.value == wm._wt.HWND(-1 if enabled else -2).value
    assert (x, y, width, height) == (0, 0, 0, 0)
    # Windows API contract: ASYNCWINDOWPOS, NOMOVE, NOSIZE, NOACTIVATE.
    assert flags == 0x4000 | 0x0002 | 0x0001 | 0x0010
