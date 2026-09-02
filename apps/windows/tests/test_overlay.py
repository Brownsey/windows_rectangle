"""Tests for windows_rectangle.ui.overlay.

The module must import without PySide6 installed (lazy import inside
`install()`). We don't exercise the widget itself in tests.
"""

import importlib


def test_overlay_module_imports_without_pyside6():
    mod = importlib.import_module("windows_rectangle.ui.overlay")
    assert hasattr(mod, "OverlayController")
    assert hasattr(mod, "install")
    assert hasattr(mod, "show_for")
    assert hasattr(mod, "hide")


def test_overlay_controller_defaults():
    from windows_rectangle.ui.overlay import OverlayController

    oc = OverlayController()
    assert oc.widget is None


def test_hide_with_no_widget_is_noop():
    from windows_rectangle.ui.overlay import OverlayController, hide

    hide(OverlayController())  # must not raise


def test_overlay_does_not_eagerly_import_pyside6():
    """Brief §5 #8 + §6: lazy Qt imports keep non-Windows CI clean.
    Importing the module must not pull PySide6 in at module-load time."""
    import sys

    sys.modules.pop("windows_rectangle.ui.overlay", None)
    pyside_was_loaded = "PySide6" in sys.modules
    importlib.import_module("windows_rectangle.ui.overlay")
    if not pyside_was_loaded:
        assert "PySide6" not in sys.modules, "ui.overlay should defer PySide6 import to install()"


def test_ensure_win32_exstyle_skips_after_first_apply(monkeypatch):
    """Second call must early-return — Win32 ex-style flags don't move
    once set, so paying GetWindowLongW per drag-zone transition is waste."""
    import sys

    import windows_rectangle.ui.overlay as overlay

    # Pretend we're on Windows for the duration of this test, regardless
    # of host platform.
    monkeypatch.setattr(sys, "platform", "win32")

    class _FakeUser32:
        def __init__(self):
            self.gets = 0
            self.sets = 0

        def GetWindowLongW(self, hwnd, idx):
            self.gets += 1
            return 0

        def SetWindowLongW(self, hwnd, idx, val):
            self.sets += 1
            return 0

    fake = _FakeUser32()
    monkeypatch.setattr(overlay, "_user32", fake)

    class _Widget:
        def winId(self):
            return 12345

    w = _Widget()
    overlay._ensure_win32_exstyle(w)
    overlay._ensure_win32_exstyle(w)
    overlay._ensure_win32_exstyle(w)
    # Only the first call should have touched user32.
    assert fake.gets == 1
    assert fake.sets == 1
    assert w._wr_exstyle_applied is True
