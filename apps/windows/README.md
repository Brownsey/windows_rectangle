# Windows Rectangle

The Windows app is a Python implementation of Rectangle-style window management
for Windows 10 and Windows 11.

## Requirements

- Windows 10 or Windows 11.
- Python 3.11 or newer available as `py` or `python`.
- PowerShell available on PATH.

## Run Locally

From the repository root:

```powershell
.\run-windows.bat
```

The launcher:

- stops any existing Windows Rectangle process,
- creates `.venv` when needed,
- installs the Windows runtime and developer dependencies,
- opens the Preferences window by default.

Useful launcher commands:

```powershell
.\run-windows.bat            # open Preferences and tray app
.\run-windows.bat tray       # start tray-only
.\run-windows.bat stop       # stop existing app instances
.\run-windows.bat test       # run pytest only
.\run-windows.bat check      # run lint, format check, mypy, and tests
.\run-windows.bat build      # build apps/windows/exe
```

Manual setup is also supported:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[win,dev]"
.\.venv\Scripts\python.exe -m windows_rectangle --open-preferences
```

Settings are saved at:

```text
%APPDATA%\windows_rectangle\config.json
```

## Build A Shareable Exe

From the repository root:

```powershell
.\build-windows-exe.bat
```

All generated Windows release files go into the `exe` folder inside this app:

```text
apps/windows/exe
```

The batch file calls the PowerShell release script. You can also run it
directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

For a fast rebuild after dependencies are installed and tests have already been
run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -NoInstall -SkipChecks
```

The build script:

- stops any existing local Windows Rectangle process,
- creates or reuses `.venv`,
- installs runtime, dev, and packaging dependencies,
- runs the full quality gate,
- builds `apps/windows/exe/WindowsRectangle.exe`,
- smoke-tests the packaged executable with `--version`,
- copies bundled runtime files into `apps/windows/exe/_internal`,
- creates a versioned zip plus SHA-256 checksums in `apps/windows/exe`.

The resulting build does not require Python or this repository. Share the zip or
the whole `apps/windows/exe` folder. Keep `WindowsRectangle.exe` beside
`_internal`; moving only the `.exe` will break the portable build. This layout
avoids the PyInstaller one-file extraction path that can show
`Failed to extract PySide6...` on some machines. Running the executable directly
opens Preferences; launch-at-login starts it tray-only.

The package entry point is also installed as:

```powershell
windows-rectangle
```

Architecture and implementation notes are in `BRIEF.md`.

## Preferences

Run `.\run-windows.bat`; the Preferences window opens on startup. You can also
open it from the tray icon menu with `Preferences...`.

The preferences window has:

- `Shortcuts`: editable key bindings for every supported window action.
- `General`: gap size, cycle timeout, almost-maximize size, drag snapping, and
  launch-at-login.

Use the search box in `Shortcuts` to filter commands. Click a shortcut to open
the `Record Shortcut` popup, then press the replacement key combo to overwrite
the row. Use `Clear` in the popup to disable that command. Changes are saved to
`%APPDATA%\windows_rectangle\config.json` and applied to the running hotkey
registrations when you click `Apply` or `Save`.

## Custom Application Workspaces

Open **Workspaces** from the tray menu to create a reusable multi-application setup.
You can capture windows that are currently open, start from the Office or RuneScape
templates, or create an empty workspace and add application rules manually.

Each rule can match an executable name, stable text in the window title, or a title
regular expression. Combining the process and title is recommended when several
windows use the same application—for example, multiple RuneLite accounts. Choose a
monitor and position preset, or drag the labeled application card on the visual
monitor canvas. Drag inside a card to move it, or drag an edge/corner to create any
custom size—layouts are not limited to halves, thirds, or presets. Alternatively,
arrange the real application windows on your desktop and select **Record current
positions** to learn their exact sizes, positions, and monitors.

Valid changes save and apply automatically. If a shortcut, matcher, or storage error
prevents saving, the editor keeps the change available for correction or retry instead
of silently discarding it. Assigning a workspace shortcut restores every matched
window later, including after the applications have been restarted.

Use **Test matches** before saving to see which rules currently match without moving
any windows. The match-status column identifies missing applications or titles.

## Custom Logo

Place custom logo files in the repository root `logo` folder before running the
app or building a release.

App logo files for the Preferences UI, in priority order:

```text
logo/windows.ico
logo/logo.ico
logo/app.ico
logo/windows.png
logo/logo.png
logo/app.png
logo/windows.webp
logo/logo.webp
logo/app.webp
```

Tray icon files, in priority order:

```text
logo/tray_logo.ico
logo/tray_logo.png
logo/tray_logo.webp
```

The Preferences window loads the first matching app logo automatically and shows
it in the visible header. The system tray icon only uses `tray_logo.ico`,
`tray_logo.png`, or `tray_logo.webp`. If no tray-specific logo exists, the tray
uses a transparent blank icon. Use an `.ico` file if you also want the generated
executable to use the custom icon. The build script bundles the full `logo`
folder into
`apps/windows/exe/_internal/logo`.

After a build, you can override the logo for that packaged copy by placing a
file in:

```text
apps/windows/exe/logo/logo.png
apps/windows/exe/logo/logo.webp
apps/windows/exe/logo/windows.ico
apps/windows/exe/logo/tray_logo.png
apps/windows/exe/logo/tray_logo.webp
apps/windows/exe/logo/tray_logo.ico
```

Keep that `logo` folder beside `WindowsRectangle.exe`.

After changing anything in the root `logo` folder, rebuild with:

```powershell
.\build-windows-exe.bat
```

Default shortcuts:

| Shortcut | Command |
| --- | --- |
| `Ctrl+Alt+Left` | Left Half |
| `Ctrl+Alt+Right` | Right Half |
| `Ctrl+Alt+Up` | Top Half |
| `Ctrl+Alt+Down` | Bottom Half |
| `Ctrl+Alt+D` | Left Third |
| `Ctrl+Alt+F` | Middle Third |
| `Ctrl+Alt+G` | Right Third |
| `Ctrl+Alt+E` | First Two Thirds |
| `Ctrl+Alt+T` | Last Two Thirds |
| `Ctrl+Alt+Shift+Enter` | Middle Majority |
| `Ctrl+Alt+U` | Top Left |
| `Ctrl+Alt+I` | Top Right |
| `Ctrl+Alt+J` | Bottom Left |
| `Ctrl+Alt+K` | Bottom Right |
| `Ctrl+Insert` | Top Left 1/6 |
| `Ctrl+Pg Up` | Top Right 3/6 |
| `Ctrl+Delete` | Bottom Left 4/6 |
| `Ctrl+Pg Down` | Bottom Right 6/6 |
| `Ctrl+Alt+Enter` | Maximize |
| `Ctrl+Alt+Shift+Up` | Maximize Height |
| `Ctrl+Alt+Shift+Right` | Maximize Width |
| `Ctrl+Alt+Shift+Space` | Always on Top |
| `Ctrl+Alt+C` | Center |
| `Ctrl+Alt+=` | Larger |
| `Ctrl+Alt+-` | Smaller |
| `Ctrl+Alt+Backspace` | Restore |
| `Ctrl+Alt+.` | Next Display |
| `Ctrl+Alt+,` | Previous Display |

## Testing

Run the full Windows test sweep from the repository root:

```powershell
.\.venv\Scripts\python -m pytest
```

Run the full lint, format, type-check, and test gate:

```powershell
.\scripts\check.ps1
```

Run the UI-focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/windows/tests/test_preferences.py apps/windows/tests/test_preferences_qt.py apps/windows/tests/test_tray.py apps/windows/tests/test_logo.py
```

`test_preferences_qt.py` uses Qt's offscreen platform to instantiate and drive
the real Preferences window automatically. It verifies shortcut search,
recording, duplicate validation, dirty state, save/apply behavior, custom logo
loading, and a non-blank rendered screenshot without requiring manual clicks.
