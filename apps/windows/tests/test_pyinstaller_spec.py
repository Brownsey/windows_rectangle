"""Tests for the PyInstaller spec file.

We don't actually run PyInstaller in CI — the bundle is too big and
the runners don't need it. But we want CI to fail loudly if someone
breaks the spec (e.g. forgets to add a newly-lazy-imported adapter to
HIDDEN, or accidentally removes the Qt excludes that keep the bundle
slim).

The spec is a Python module evaluated by PyInstaller with `Analysis`,
`PYZ`, `EXE` injected as builtins. We exec it with those stubbed out
and inspect the captured kwargs.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = REPO_ROOT / "windows_rectangle.spec"


class _Capture:
    """Records the kwargs each PyInstaller pseudo-class is called with."""

    def __init__(self):
        self.analysis: dict | None = None
        self.exe: dict | None = None

    def make_analysis(self):
        capture = self

        class Analysis:
            def __init__(self, *args, **kwargs):
                capture.analysis = {"args": args, "kwargs": kwargs}
                # PyInstaller's Analysis exposes attributes a PYZ + EXE need.
                self.pure = []
                self.zipped_data = []
                self.scripts = []
                self.binaries = []
                self.zipfiles = []
                self.datas = []

        return Analysis

    def make_pyz(self):
        class PYZ:
            def __init__(self, *args, **kwargs):
                pass

        return PYZ

    def make_exe(self):
        capture = self

        class EXE:
            def __init__(self, *args, **kwargs):
                capture.exe = {"args": args, "kwargs": kwargs}

        return EXE


def _exec_spec() -> _Capture:
    capture = _Capture()
    namespace = {
        "Analysis": capture.make_analysis(),
        "PYZ": capture.make_pyz(),
        "EXE": capture.make_exe(),
    }
    exec(compile(SPEC.read_text(), str(SPEC), "exec"), namespace)
    return capture


def test_spec_file_exists():
    assert SPEC.is_file()


def test_spec_evaluates_without_error():
    _exec_spec()


def test_analysis_targets_main_module():
    cap = _exec_spec()
    assert cap.analysis is not None
    scripts = cap.analysis["args"][0]
    assert any("__main__.py" in str(s) for s in scripts)


def test_lazy_adapter_imports_are_hidden():
    """Every adapter is lazy-imported inside a function, so PyInstaller's
    static analysis won't find them — they MUST be in hiddenimports."""
    cap = _exec_spec()
    hidden = cap.analysis["kwargs"]["hiddenimports"]
    for must in (
        "windows_rectangle.adapters.win32_windows",
        "windows_rectangle.adapters.win32_hotkeys",
        "windows_rectangle.adapters.win32_mousehook",
        "windows_rectangle.adapters.winreg_autostart",
        "windows_rectangle.adapters.single_instance",
        "windows_rectangle.adapters.win_dpi",
        "windows_rectangle.adapters.json_config",
        "windows_rectangle.ui.prefs_dialog",
        # Tray menu's cheat-sheet popup lazy-imports this.
        "windows_rectangle.ui.cheat_sheet",
        # Tray's "Binding status…" popup lazy-imports this.
        "windows_rectangle.ui.binding_status_view",
        # --check-install lazy-imports the diagnostics module.
        "windows_rectangle.diagnostics",
        # __main__'s _setup_logging lazy-imports this.
        "windows_rectangle.log_file",
        # --print-monitors lazy-imports this.
        "windows_rectangle.monitors_view",
        # --import-config --dry-run lazy-imports this.
        "windows_rectangle.settings_diff",
    ):
        assert must in hidden, f"{must} missing from hiddenimports"


def test_heavyweight_qt_modules_excluded():
    """Brief §8 says to exclude unused Qt modules to keep the bundle slim."""
    cap = _exec_spec()
    excludes = cap.analysis["kwargs"]["excludes"]
    # Spot-check the biggest offenders.
    for must in (
        "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQml",
        "PySide6.QtNetwork",
    ):
        assert must in excludes, f"{must} should be excluded"


def test_exe_is_windowed_not_console():
    """Tray-only app — no console window should pop up on launch."""
    cap = _exec_spec()
    assert cap.exe["kwargs"]["console"] is False


def test_exe_has_branded_name():
    cap = _exec_spec()
    assert cap.exe["kwargs"]["name"] == "WindowsRectangle"
