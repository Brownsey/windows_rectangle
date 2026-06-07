# Windows Rectangle

A Rectangle-for-Windows window manager — a feature-parity clone of the macOS
[Rectangle](https://github.com/rxhanson/Rectangle) app, built in Python and
runnable on Windows 10/11.

Snap windows to halves, quarters, thirds, sixths, maximize, almost-maximize,
restore (undo) and more — all via fully rebindable keyboard shortcuts.
Drag a window to a screen edge for live snap previews.

---

## Quick start (for users)

You have two ways to run Windows Rectangle:

### Option A — Run the prebuilt .exe (recommended)

1. Open a PowerShell window in this directory.
2. Run the one-shot build script. It installs PyInstaller + PySide6 + pywin32
   into your current Python and produces a single-file `.exe`:

   ```powershell
   .\Build-Exe.ps1
   ```

3. Double-click `dist\WindowsRectangle.exe`. A tray icon appears in the
   notification area (small blue tile with a 2×2 grid — right-click it).
4. Right-click the tray icon → **Preferences…** to rebind shortcuts,
   change the gap, enable launch-at-login, etc.
5. Right-click the tray icon → **Quit** to fully stop the app (all
   shortcuts and the mouse hook are released).

Windows SmartScreen may warn the first time you run an unsigned `.exe` —
click **More info → Run anyway**. Code-signing is a future to-do.

### Option B — Run from source

1. Install Python 3.11+ and the runtime extras:

   ```powershell
   pip install -e ".[win]"
   ```

2. Launch:

   ```powershell
   python -m windows_rectangle
   ```

   Or, if you don't have PySide6 installed, run the stdlib-only fallback
   that exposes hotkeys without a tray:

   ```powershell
   python -m windows_rectangle --headless
   ```

---

## Default shortcuts

| Action | Default shortcut |
|---|---|
| Left / Right / Top / Bottom half | `Ctrl+Alt+←/→/↑/↓` |
| Top-Left / Top-Right quarter | `Ctrl+Alt+U` / `Ctrl+Alt+I` |
| Bottom-Left / Bottom-Right quarter | `Ctrl+Alt+J` / `Ctrl+Alt+K` |
| First / Center / Last third | `Ctrl+Alt+D` / `Ctrl+Alt+F` / `Ctrl+Alt+G` |
| First / Last two-thirds | `Ctrl+Alt+E` / `Ctrl+Alt+T` |
| Maximize | `Ctrl+Alt+Enter` |
| Maximize height | `Ctrl+Alt+Shift+↑` |
| Almost-maximize (~85%) | `Ctrl+Alt+Shift+Enter` |
| Center (no resize) | `Ctrl+Alt+C` |
| Larger / smaller | `Ctrl+Alt+=` / `Ctrl+Alt+-` |
| Restore (undo) | `Ctrl+Alt+Backspace` |
| Next / previous display | `Ctrl+Alt+.` / `Ctrl+Alt+,` |

Every binding is rebindable from **Preferences…**. Clearing a row's combo
cell unbinds that action.

---

## Tips

- **Repeat-key cycling.** Pressing a half/third shortcut twice cycles between
  related positions, exactly like macOS Rectangle. The idle timeout is
  configurable in Preferences.
- **Drag-to-edge.** Drag a window to a screen edge or corner and a translucent
  preview shows where it will land on release. Toggle the feature in
  Preferences.
- **Gap between tiled windows.** Set in Preferences; takes effect immediately
  without restart.
- **Per-monitor DPI.** The app declares Per-Monitor-V2 DPI awareness on
  startup, so geometry stays correct on mixed-DPI multi-monitor setups.
- **Admin windows.** Windows blocks non-admin processes from moving windows
  owned by elevated processes (UIPI). If a hotkey seems to do nothing on an
  admin window, that's why. Run Windows Rectangle elevated if you need it.
- **Launch at login.** Toggle in the tray menu or Preferences; persists to
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

---

## Configuration

Settings are stored as JSON at:

```
%APPDATA%\WindowsRectangle\config.json
```

Editing the file by hand works — the app reloads on next launch. The
Preferences dialog is the supported path; hand-editing is for power users
and headless setups.

---

## Building a custom .exe

The repo ships with a tuned PyInstaller spec (`windows_rectangle.spec`).
The `Build-Exe.ps1` / `Build-Exe.bat` scripts call it. To customise:

- **Onefile vs onedir.** `--onefile` (current) gives a single `.exe` with
  ~1-2s extraction lag on launch. Switch to `--onedir` for faster cold
  start by editing the spec (see the header comment).
- **Icon.** Drop a `.ico` next to the spec and uncomment the `icon=`
  line in the EXE() block.
- **Excluded Qt modules.** The spec already excludes WebEngine, Multimedia,
  Qml, etc. — see `EXCLUDES` at the top.

---

## Architecture, brief, and contributing

For the technical brief, architecture, and design decisions see
[`BRIEF.md`](BRIEF.md). Contributors should run the test suite:

```powershell
pip install -e ".[dev]"
pytest
```

407+ tests, no Windows required for the `core/` layer (adapters do require
Windows). License is MIT; see `THIRD_PARTY_NOTICES.md` for upstream
attribution.
