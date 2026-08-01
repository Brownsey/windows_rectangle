# Rectangle Desktop Apps

This repository contains two platform apps:

- `apps/mac/Rectangle`: a vendored fork snapshot of the macOS Rectangle app.
- `apps/windows`: the Python Windows Rectangle implementation.

The macOS app is copied from the upstream Rectangle repository so builds do not
depend on fetching the application source from upstream at release time. The
Windows app remains a separate implementation that follows Rectangle's behavior
and shortcut model on Windows.

## Shared Logo

Custom logo files live in the repository root `logo` folder. The same folder is
used by both platform builds.

Recommended cross-platform setup:

```text
logo/logo.png
logo/logo.webp
logo/windows.ico
logo/mac/logo.png
logo/mac/logo.webp
```

Use a 1024x1024 PNG or WebP for `logo/logo.*` or `logo/mac/logo.*`. PNG remains
the preferred format for the widest tooling compatibility. Use
`logo/windows.ico` when you want the Windows executable file itself to display
a custom icon. More detail is in `logo/README.md`.

## macOS App

Source: `apps/mac/Rectangle`

Upstream project: <https://github.com/rxhanson/Rectangle>

Snapshot commit: `6cfcb4720b3a6f83df82a8896a3da4751e90ca4e`

Upstream commit date: `2026-07-28 22:12:35 -0400`

Requirements:

- macOS with Xcode installed.
- Xcode command line tools available through `xcodebuild`.
- Accessibility permission granted to the built app the first time it runs.

Run the fork locally from the repository root:

```bash
bash build-mac-release.sh
open apps/mac/build/Build/Products/Release/Rectangle.app
```

To build a local downloadable zip on macOS:

```bash
bash build-mac-release.sh
```

The output is written to `apps/mac/exe/Rectangle-macOS.zip`, with a SHA-256
checksum beside it. For distribution outside local testing, use an Apple
Developer signing identity and notarize the resulting app.

To customize the macOS logo, place one of these before building:

```text
logo/mac/AppIcon.appiconset
logo/mac/logo.png
logo/mac/logo.webp
logo/logo.png
logo/logo.webp
```

If a PNG or WebP is provided, `apps/mac/build-release.sh` uses macOS `sips` to
generate the required app icon sizes automatically for the build. The script
restores the vendored Rectangle icon assets after the build completes.

## Windows App

Source: `apps/windows/windows_rectangle`

Tests: `apps/windows/tests`

Requirements for local development:

- Windows 10 or Windows 11.
- Python 3.11 or newer available as `py` or `python`.
- PowerShell available on PATH.

Run the app locally from the repository root:

```powershell
.\run-windows.bat
```

The launcher creates `.venv` when needed, installs dependencies, stops any
existing Windows Rectangle instance, and opens the Preferences window.

Useful local run commands:

```powershell
.\run-windows.bat            # open Preferences and tray app
.\run-windows.bat tray       # start tray-only
.\run-windows.bat stop       # stop existing app instances
.\run-windows.bat test       # run pytest only
.\run-windows.bat check      # run lint, format check, mypy, and tests
```

Manual development commands, if you do not want to use the batch file:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[win,dev]"
.\.venv\Scripts\python.exe -m windows_rectangle --open-preferences
.\.venv\Scripts\python.exe -m pytest
```

Build a shareable Windows executable with:

```powershell
.\build-windows-exe.bat
```

All generated Windows release files are placed in the `exe` folder inside the
Windows app:

```text
apps/windows/exe
```

The full build command above is equivalent to:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

For a faster rebuild after dependencies have already been installed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -NoInstall -SkipChecks
```

The build creates a portable executable folder:

```text
apps/windows/exe/WindowsRectangle.exe
apps/windows/exe/_internal/
apps/windows/exe/WindowsRectangle.exe.sha256
apps/windows/exe/WindowsRectangle-<version>-windows-x64.zip
apps/windows/exe/WindowsRectangle-<version>-windows-x64.zip.sha256
```

The build bundles Python and runtime dependencies, so the user does not need
this repository or a Python environment. Share the zip or the whole
`apps/windows/exe` folder. Keep `WindowsRectangle.exe` beside `_internal`; this
portable layout avoids the PyInstaller one-file extraction path that can produce
`Failed to extract PySide6...` errors on some machines.

To customize the Windows logo, place one of these before running
`.\build-windows-exe.bat`:

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

The Windows tray and Preferences UI load the logo automatically. The build also
bundles the `logo` folder into `apps/windows/exe/_internal/logo`. If you need to
override the logo after building, create `apps/windows/exe/logo/logo.png`,
`apps/windows/exe/logo/logo.webp`, or `apps/windows/exe/logo/windows.ico` next
to the executable folder.

The root `pyproject.toml` points packaging and tests at `apps/windows`, so the
existing Python module name remains `windows_rectangle`.

The Windows Preferences window edits every supported command shortcut and the
general settings. It opens on normal launcher startup and is also available from
the tray menu via `Preferences...`. Use the shortcut search box to filter
commands. Click a shortcut to open the `Record Shortcut` popup, press the
replacement key combo, then click `Apply` or `Save`. Use `Clear` in the popup to
disable that command. Settings are stored in `%APPDATA%\windows_rectangle\config.json`.
The active default shortcut profile is documented in `apps/windows/README.md`.

Run the full Windows quality gate with:

```powershell
.\scripts\check.ps1
```

The root GitHub Actions workflow runs the same gate on `windows-latest`.

## Credits

Full credit for the macOS Rectangle app goes to the original Rectangle project:

- Rectangle by Ryan Hanson: <https://github.com/rxhanson/Rectangle>
- Rectangle is MIT licensed. See `apps/mac/Rectangle/LICENSE`.
- Rectangle is based on Spectacle by Eric Czarny.
- Rectangle uses MASShortcut and Sparkle, as documented in the upstream
  `apps/mac/Rectangle/README.md`.
- App icon credits and community contributor credits remain in the upstream
  README copied into `apps/mac/Rectangle/README.md`.

The Windows app was built to match Rectangle's behavior on Windows and credits
Rectangle in `THIRD_PARTY_NOTICES.md`.
