# Portable Windows build. One directory avoids extracting Qt on every launch.
# Invoked by scripts/build-windows.ps1; keep module exclusions and assets here.
# ruff: noqa
# mypy: ignore-errors
import os
from pathlib import Path

ROOT = Path(SPECPATH)

# Hidden imports: modules imported lazily inside functions (so
# PyInstaller's static analysis misses them).
HIDDEN = [
    # Win32 adapters — imported only inside app.bind_win32().
    "windows_rectangle.adapters.json_config",
    "windows_rectangle.adapters.single_instance",
    "windows_rectangle.adapters.win32_hotkeys",
    "windows_rectangle.adapters.win32_mousehook",
    "windows_rectangle.adapters.win32_windows",
    "windows_rectangle.adapters.win_dpi",
    "windows_rectangle.adapters.winreg_autostart",
    # Prefs dialog — lazy import inside open_prefs_window's factory.
    "windows_rectangle.ui.prefs_dialog",
    # Tray's cheat-sheet popup imports this lazily from inside the
    # menu action handler; PyInstaller's static analysis won't see it
    # unless we list it here.
    "windows_rectangle.ui.cheat_sheet",
    # Tray's "Binding status…" popup likewise lazy-imports the formatter.
    "windows_rectangle.ui.binding_status_view",
    "windows_rectangle.ui.workspace_editor",
    "windows_rectangle.ui.workspaces_dialog",
    "windows_rectangle.ui.workspace_canvas",
    "windows_rectangle.core.workspace_presets",
    "windows_rectangle.core.workspace_templates",
    # --check-install subcommand lazy-imports the diagnostics module.
    "windows_rectangle.diagnostics",
    # __main__'s _setup_logging lazy-imports this for the rotating file handler.
    "windows_rectangle.log_file",
    # --print-monitors lazy-imports this formatter.
    "windows_rectangle.monitors_view",
    # --import-config --dry-run lazy-imports the diff formatter.
    "windows_rectangle.settings_diff",
    # PySide6 plugins that QApplication needs at runtime.
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

# Brief §8: "exclude unused Qt modules" — keep the bundle slim.
# We're tray + dialog + overlay only — no WebEngine, no Multimedia, etc.
EXCLUDES = [
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
    # Test frameworks accidentally pulled in via dev installs.
    "pytest",
    "ruff",
    "mypy",
]

# Match Windows DLL lookup before PATH tools. Qt uses the system ICU ABI;
# unrelated native tools can provide an incompatible icuuc.dll on PATH.
original_path = os.environ.get("PATH", "")
os.environ["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32") + os.pathsep + original_path
try:
    a = Analysis(
        [str(ROOT / "packaging/windows/WindowsRectangle.py")],
        pathex=[str(ROOT / "apps/windows")],
        binaries=[],
        datas=[(str(ROOT / "logo"), "logo"), (str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")],
        hiddenimports=HIDDEN,
        hookspath=[],
        runtime_hooks=[],
        excludes=EXCLUDES,
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        noarchive=False,
    )
finally:
    os.environ["PATH"] = original_path

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name="WindowsRectangle",
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # SmartScreen + AV are friendlier without UPX.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # Tray-only app — no console window on launch.
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=next((str(ROOT / "logo" / name) for name in
               ("windows.ico", "logo.ico", "app.ico")
               if (ROOT / "logo" / name).is_file()), None),
)

collect = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="WindowsRectangle")
