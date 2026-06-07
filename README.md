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
5. Other tray menu items:
   - **Pause shortcuts** — checkable. Unregisters every hotkey at the OS
     level so other apps (full-screen games, RDP sessions) get the keys
     back. Uncheck to resume. Settings are kept; no reload required.
     The tooltip appends ` • paused` while active.
   - **Cheat sheet…** — at-a-glance list of every action and its current combo.
   - **Binding status…** — shows "X of Y shortcuts bound" plus the specific
     combos and error messages for any failures (e.g. another app already
     owns `Ctrl+Alt+←`). Hover the tray icon for the same count in the tooltip.
   - **Reload config from disk** — re-reads the JSON after you hand-edit it.
   - **Open config folder…** — jumps to `%APPDATA%\windows_rectangle\` in
     Explorer (created if missing).
   - **Open log file…** — opens the rotating log file (or its folder if
     nothing has been logged yet). Attach the contents to a bug report.
   - **About…** — version + license.
6. Preferences dialog has a **Reset shortcuts to defaults** button under
   the shortcuts table — handy after experimenting with custom combos.
7. Right-click the tray icon → **Quit** to fully stop the app (all
   shortcuts and the mouse hook are released).

Windows SmartScreen may warn the first time you run an unsigned `.exe` —
click **More info → Run anyway**. Code-signing is a future to-do.

Want it findable via the Start Menu / search? Pass `-InstallStartMenuShortcut`.
Want to build *and* run in one step? Pass `-Launch`:

```powershell
.\Build-Exe.ps1 -InstallStartMenuShortcut -Launch
```

The script verifies Python ≥ 3.11 up front and refuses to build over a
running `WindowsRectangle.exe` (it tells you to quit the tray first).

### Option B — Run from source

For contributors who want the tray running without producing an .exe.
One shot:

```powershell
.\Run-Dev.ps1
```

The script installs PySide6 + pywin32 if needed, then launches
`python -m windows_rectangle`. Pass `-Headless` to skip Qt and run the
stdlib-only fallback (hotkeys + dispatcher only, no tray):

```powershell
.\Run-Dev.ps1 -Headless
```

You can also do it by hand:

```powershell
pip install -e ".[win]"
python -m windows_rectangle
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

Editing the file by hand works — the Preferences dialog is the supported
path, but you can also use tray → **Reload config from disk** after a
hand-edit to pick up changes without restarting the app.

### Quick CLI helpers

These short-circuit before any Win32 wiring, so they're safe to run while
a tray copy is open:

```powershell
# Self-diagnostic — version, dep importability, config path
.\dist\WindowsRectangle.exe --check-install

# Same, but JSON for scripting / CI
.\dist\WindowsRectangle.exe --check-install-json

# Print the on-disk config path
.\dist\WindowsRectangle.exe --print-config-path

# Print every action and its currently-configured shortcut
.\dist\WindowsRectangle.exe --list-shortcuts

# Snapshot your settings to a portable file (backup / new machine)
.\dist\WindowsRectangle.exe --export-config "C:\Backup\winrect.json"

# Restore settings from a snapshot on this machine — takes effect on next launch
.\dist\WindowsRectangle.exe --import-config "C:\Backup\winrect.json"
```

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

## Uninstalling

Symmetric counterpart to `Build-Exe.ps1`:

```powershell
.\Uninstall-WindowsRectangle.ps1
```

This stops a running tray copy (asking it to shut down cleanly first),
removes the per-user Start-Menu shortcut, and removes the `HKCU\…\Run`
"Launch at login" registry entry. Your config is kept; pass
`-PurgeConfig` to also delete `%APPDATA%\windows_rectangle\`.

The `.exe` and source tree are left in place — delete them by hand if
you want them gone too.

## Troubleshooting

- **Tray icon doesn't appear.** Make sure your tray "Notification area"
  isn't hiding it. Open the up-arrow in the taskbar and drag the icon
  to a permanent slot. If the .exe seems to have exited, run it from a
  PowerShell window so you can see the startup log.
- **A shortcut does nothing.** Right-click the tray → **Binding status…**
  — if the action is listed under "Failed", another app already owns
  that combo. Rebind in **Preferences…** or close the conflicting app.
- **Shortcut works on most windows but not on one specific app.** That
  app is probably running elevated (Task Manager → Details → "Elevated"
  column). Windows blocks non-admin processes from moving elevated
  windows (UIPI). Run Windows Rectangle as administrator if you need it.
- **PyInstaller build fails with PermissionError.** The script now
  blocks this — but if you bypass the check, the cause is a live
  WindowsRectangle.exe locking the file. Quit it via the tray menu and
  re-run the build.
- **SmartScreen blocks the .exe.** Click **More info → Run anyway**.
  The build isn't code-signed yet (see roadmap in `BRIEF.md` §6).
- **App says PySide6 missing** when running from source. Re-run
  `.\Run-Dev.ps1` without `-NoInstall`, or install manually with
  `pip install PySide6 pywin32`.

## What's new

See [`CHANGELOG.md`](CHANGELOG.md) for the user-visible release log.

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
