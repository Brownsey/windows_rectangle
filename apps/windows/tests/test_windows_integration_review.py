"""Disposable native resources for independent Windows adapter validation."""

import ctypes
import sys
from ctypes import wintypes
from uuid import uuid4

import pytest

from windows_rectangle.adapters.json_config import JsonConfigStore
from windows_rectangle.adapters.single_instance import WindowsMutexSingleInstance
from windows_rectangle.adapters.win32_hotkeys import Win32Hotkeys
from windows_rectangle.adapters.win32_mousehook import Win32MouseHook
from windows_rectangle.adapters.win32_windows import Win32WindowManager
from windows_rectangle.adapters.win_dpi import enable_dpi_awareness
from windows_rectangle.app import build
from windows_rectangle.core.actions import Action
from windows_rectangle.core.geometry import Rect
from windows_rectangle.ports.config_store import Settings
from windows_rectangle.ui import preferences

from .conftest import FakeWindowManager, make_monitor

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows native integration")


def test_own_window_moves_to_requested_visible_rect():
    enable_dpi_awareness()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    manager = Win32WindowManager()
    monitor = next(item for item in manager.list_monitors() if item.is_primary)
    area = monitor.work_area
    target = Rect(area.x + 80, area.y + 80, 480, 320)
    handle = user32.CreateWindowExW(
        0,
        "STATIC",
        f"Windows Rectangle validation {uuid4().hex}",
        0x10CF0000,
        target.x + 30,
        target.y + 30,
        480,
        320,
        None,
        None,
        kernel32.GetModuleHandleW(None),
        None,
    )
    assert handle, ctypes.get_last_error()
    try:
        assert manager.is_window_valid(handle)
        assert manager.set_window_rect(handle, target)
        visible = manager.get_window_rect(handle)
        assert abs(visible.x - target.x) <= 2
        assert abs(visible.y - target.y) <= 2
        assert abs(visible.width - target.width) <= 2
        assert abs(visible.height - target.height) <= 2
        assert manager.set_always_on_top(handle, True)
        assert manager.is_always_on_top(handle)
        assert manager.get_window_rect(handle) == visible
        assert manager.set_always_on_top(handle, False)
        assert not manager.is_always_on_top(handle)
        assert manager.get_window_rect(handle) == visible
    finally:
        assert user32.DestroyWindow(handle)


def test_unique_mutex_and_hotkey_release():
    name = f"Local\\WindowsRectangleReview-{uuid4()}"
    first = WindowsMutexSingleInstance(name)
    second = WindowsMutexSingleInstance(name)
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()
    assert second.acquire()
    second.release()

    combo = "ctrl+alt+shift+f24"
    hotkeys = Win32Hotkeys()
    try:
        hotkey_id = hotkeys.register(combo, lambda: None)
        assert hotkey_id > 0
        hotkeys.unregister(hotkey_id)
    finally:
        hotkeys.shutdown()
    assert not hotkeys._thread.is_alive()


def test_mouse_hook_installs_and_stops_without_input():
    hook = Win32MouseHook(lambda _kind, _x, _y: None)
    try:
        assert hook._hook_handle
        assert hook._thread.is_alive()
    finally:
        hook.shutdown()
    assert not hook._thread.is_alive()
    assert not hook._hook_handle


def test_live_preferences_search_save_and_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if hasattr(app, "_windows_rectangle_preferences"):
        del app._windows_rectangle_preferences
    store = JsonConfigStore(tmp_path / "config.json")
    windows = FakeWindowManager(monitors=[make_monitor(1, 0, 0, 1920, 1080)])
    ctx = build(Settings(drag_to_edge_enabled=False), windows, config_store=store)
    controller = preferences.show(ctx)
    try:
        app.processEvents()
        screenshot = tmp_path / "preferences.png"
        assert controller.window.grab().save(str(screenshot), "PNG")
        print(f"SCREENSHOT: {screenshot}")

        search = controller.window.findChild(QtWidgets.QLineEdit, "shortcutSearch")
        search.setText("six top")
        app.processEvents()
        assert controller.rows[Action.TOP_LEFT_SIXTH].isVisible()
        assert not controller.rows[Action.LEFT_HALF].isVisible()
        search.clear()

        monkeypatch.setattr(
            preferences,
            "_record_shortcut",
            lambda *_args: QtGui.QKeySequence("Ctrl+Alt+L"),
        )
        controller.shortcut_widgets[Action.LEFT_HALF].click()
        controller.gap_spin.setValue(13)
        app.processEvents()
        assert controller.dirty
        assert controller.save_button.isEnabled()
        controller.save_button.click()
        app.processEvents()
        assert not controller.window.isVisible()
        assert store.load().gap == 13
        assert store.load().shortcuts[Action.LEFT_HALF] == "ctrl+alt+l"
        assert ctx.settings.gap == 13
        assert not app.quitOnLastWindowClosed()

        reopened = preferences.show(ctx)
        app.processEvents()
        assert reopened is controller
        assert reopened.gap_spin.value() == 13
        assert reopened.window.isVisible()
    finally:
        controller.dirty = False
        controller.window.hide()
        controller.window.deleteLater()
        del app._windows_rectangle_preferences
        QtCore.QCoreApplication.processEvents()
