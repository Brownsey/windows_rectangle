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

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC = REPO_ROOT / "windows_rectangle.spec"


class _Capture:
    """Records the kwargs each PyInstaller pseudo-class is called with."""

    def __init__(self):
        self.analysis: dict | None = None
        self.exe: dict | None = None
        self.collect: dict | None = None
        self.analysis_path = ""

    def make_analysis(self):
        capture = self

        class Analysis:
            def __init__(self, *args, **kwargs):
                capture.analysis = {"args": args, "kwargs": kwargs}
                capture.analysis_path = os.environ.get("PATH", "")
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

    def make_collect(self):
        def collect(*args, **kwargs):
            self.collect = {"args": args, "kwargs": kwargs}

        return collect


def _exec_spec() -> _Capture:
    capture = _Capture()
    namespace = {
        "Analysis": capture.make_analysis(),
        "PYZ": capture.make_pyz(),
        "EXE": capture.make_exe(),
        "COLLECT": capture.make_collect(),
        "SPECPATH": str(REPO_ROOT),
    }
    exec(compile(SPEC.read_text(), str(SPEC), "exec"), namespace)
    return capture


def test_spec_file_exists():
    assert SPEC.is_file()


def test_spec_evaluates_without_error():
    _exec_spec()


def test_analysis_prefers_windows_system_dlls_over_unrelated_path_tools(monkeypatch):
    before = "C:\\unrelated-native-tools"
    monkeypatch.setenv("PATH", before)
    cap = _exec_spec()
    system32 = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    assert cap.analysis_path.split(os.pathsep)[0].casefold() == system32.casefold()
    assert os.environ["PATH"] == before


def test_analysis_entrypoint_runs_as_a_script():
    cap = _exec_spec()
    assert cap.analysis is not None
    scripts = cap.analysis["args"][0]
    assert len(scripts) == 1
    result = subprocess.run(
        [sys.executable, scripts[0], "--check-install"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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


def test_build_is_portable_without_startup_extraction_and_includes_assets():
    cap = _exec_spec()
    assert cap.exe["kwargs"].get("exclude_binaries") is True
    assert cap.collect is not None
    assert cap.collect["kwargs"]["name"] == "WindowsRectangle"
    assert any(destination == "logo" for _, destination in cap.analysis["kwargs"]["datas"])
    assert any(destination == "." for _, destination in cap.analysis["kwargs"]["datas"])
