"""Tests for windows_rectangle.ui.prefs_dialog.

The QDialog itself can't be tested without PySide6 + a display, so this
file's job is the import-safety check: the module must be importable
without PySide6 installed (lazy import inside `build_dialog`), and it
must expose the expected entry point. Brief §6 / CI: the Ubuntu test
job runs on a clean Python without PySide6, and prefs_dialog must not
trip ImportError at collection time.
"""

import importlib


def test_prefs_dialog_module_imports_without_pyside6():
    mod = importlib.import_module("windows_rectangle.ui.prefs_dialog")
    assert hasattr(mod, "build_dialog")
    # build_dialog should be callable; we don't actually invoke it (would
    # need a QApplication + display).
    assert callable(mod.build_dialog)


def test_prefs_dialog_does_not_eagerly_import_pyside6():
    """Brief §5 #8 + §6: lazy Qt imports keep non-Windows CI clean. The
    module top-level must not pull PySide6 just from `import`."""
    import sys

    # Wipe any prior import.
    sys.modules.pop("windows_rectangle.ui.prefs_dialog", None)
    pyside_was_loaded = "PySide6" in sys.modules
    importlib.import_module("windows_rectangle.ui.prefs_dialog")
    if not pyside_was_loaded:
        # We didn't bring PySide6 in by importing the module.
        assert "PySide6" not in sys.modules, (
            "ui.prefs_dialog should defer PySide6 import to build_dialog()"
        )
