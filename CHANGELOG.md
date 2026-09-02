# Changelog

User-facing notable changes. The technical brief lives in [`BRIEF.md`](BRIEF.md);
this file tracks what shipped from a user's point of view.

The project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dates are absolute (YYYY-MM-DD). Versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- One-shot **`Build-Exe.ps1`** / `Build-Exe.bat` build the single-file
  `dist\WindowsRectangle.exe` and auto-install the runtime deps
  (PyInstaller, PySide6, pywin32). `-InstallStartMenuShortcut` drops a
  per-user `.lnk` into the Start Menu; `-Launch` starts the freshly-
  built .exe so a contributor can install + run in one step. The
  script refuses < Python 3.11 and won't try to overwrite a running
  WindowsRectangle.exe.
- **`Uninstall-WindowsRectangle.ps1`** — stops a live tray copy,
  removes the per-user Start-Menu shortcut, removes the
  `HKCU\…\Run\WindowsRectangle` autostart entry. Pass `-PurgeConfig`
  to also delete `%APPDATA%\windows_rectangle\`.
- **`--print-config-path`** and **`--list-shortcuts`** CLI subcommands
  short-circuit before any Win32 wiring, so they're safe to run while
  a tray copy is open.
- **`--check-install`** / **`--check-install-json`** self-diagnostic
  — version, Python info, dep importability for `core/`, `ports/`,
  `adapters/json_config`, plus optional PySide6 / pywin32 probes, and
  the on-disk config path. Exits 0/1 so it pipes into CI. Backed by
  `windows_rectangle.diagnostics` (pure, 100% test-covered).
- **`CONTRIBUTING.md`** — fast-path commands, project layout,
  conventions for lazy Qt imports + pure formatters, PR checklist.
- **Rotating log file** at `%APPDATA%\windows_rectangle\windows_rectangle.log`
  (1 MB × 4 generations = ≤ 4 MB total). Installed by `_setup_logging`
  in `__main__`; idempotent so repeat startup paths don't double-up
  handlers. Tray gets a matching **"Open log file…"** menu item that
  opens the log in the user's default text app (or its parent folder
  if nothing has been logged yet).

- **`--export-config <PATH>`** snapshots the current settings to a
  portable JSON file (uses the same atomic write path as `save`).
- **`--import-config <PATH>`** loads settings from a snapshot and
  persists them as the new config. Both flags short-circuit before
  `bind_win32`, so they're safe to use while a tray copy is open.
  Designed for backups + moving config between machines.
- **`--print-monitors`** / **`--print-monitors-json`** dump every
  monitor's bounds, work area, primary flag, and inferred taskbar
  reservation. Helps users debug why an action lands somewhere
  unexpected on multi-monitor / mixed-DPI setups. Backed by the
  pure `monitors_view` formatter (test-covered).

- **`Doctor.ps1`** — one-shot support-package collector. Runs the
  bundled diagnostic flags + tails the log + records OS info into a
  text file users can attach to a bug report. `-Show` opens it.
- **`--import-config --dry-run`** previews the per-field changes
  (gap, drag-to-edge, every shortcut, etc.) without touching disk.
  Backed by the pure `settings_diff` formatter (test-covered).
- `--export-config` + `--import-config` are now mutually exclusive
  (argparse error rather than silent double-action). `--dry-run`
  requires `--import-config`.

### Changed
- `--help` output is reorganised into **runtime**, **informational**,
  and **migration** argument groups with an examples epilog. The
  argument set hasn't changed; only the rendering has.
- `Build-Exe.ps1` runs `WindowsRectangle.exe --check-install` as the
  final step so a missing-hidden-import in the bundle fails the build
  loudly instead of waiting for a user to discover it at runtime.
- `JsonConfigStore.load` now logs a warning (with the path + reason)
  when the config JSON is unreadable, instead of silently falling back
  to defaults. The user gets a searchable log line pointing at the
  file to fix.
- `BindingReport` gains an explicit `paused: bool` flag plus a
  `would_bind_count` property. `pause_hotkeys` no longer squashes
  the previously-bound entries into `failed` with a "paused"
  string; it sets the flag and the Binding Status dialog renders a
  greyed-out "Would re-register on resume" section instead of the
  misleading red "Failed" list. The tooltip stays "X/Y bound" with
  the denominator stable across pause/resume.
- `JsonConfigStore.parse_path(source)` is now the public way to read a
  Settings without persisting; `import_from` reuses it and
  `--import-config --dry-run` calls it directly instead of poking
  into the private `_from_dict`.

### Changed
- Tray tooltip now appends ` • paused` when the user has clicked
  **Pause shortcuts**, so an `0/22 bound` count looks intentional
  instead of broken.

### Fixed
- `JsonConfigStore._atomic_write` now closes the temp-file handle
  before unlinking on the error path; the previous code relied on
  `os.unlink` succeeding while the handle was still open, which fails
  with `PermissionError` on Windows and silently leaked the `.tmp`
  file into the config folder. Locked in by the new
  `test_export_is_atomic`.
- **Troubleshooting** section in `README.md` covering tray-icon
  visibility, hotkey conflicts, elevated windows, PyInstaller lock
  errors, SmartScreen, and missing PySide6.
- **`Run-Dev.ps1`** / `Run-Dev.bat` for contributors: launches
  `python -m windows_rectangle` after probing the runtime deps. Forwards
  `-Headless` and `-LogLevel`.
- **Tray cheat sheet** — every action and its current shortcut in a
  popup; pure formatter (`ui.cheat_sheet`) reused by tests.
- **Tray "Binding status…"** dialog and tooltip — "X of Y shortcuts
  bound" with a per-failure breakdown so users can see which combo
  another app is already holding.
- **Tray "Reload config from disk"** for power users who hand-edit
  `%APPDATA%\windows_rectangle\config.json`. Toast confirms success.
- **Tray "Open config folder…"** opens the config directory in Explorer
  (creates it if missing).
- **Tray "Pause shortcuts"** (checkable) — unregisters every hotkey at
  the OS level while keeping Settings intact; uncheck to resume. Useful
  for full-screen games and RDP sessions.
- **Preferences "Reset shortcuts to defaults"** button — restores the
  Rectangle-default keymap without touching gap / drag-to-edge / etc.
- **First-run welcome balloon** — fires once when `bind_win32` detects
  no existing config file; defaults are then persisted so subsequent
  launches are quiet.
- **About…** tray entry with version + license.
- New **`README.md`** as the user-facing front door (the technical brief
  remains in `BRIEF.md`).

### Changed
- Tray icon is now a programmatic blue 2×2 tile glyph (replaces the
  white-square placeholder); no `.ico` asset shipped — drawing happens
  at runtime so the build pipeline has one fewer file to worry about.
- Tray tooltip now reads `Windows Rectangle • Npx gap • X/Y shortcuts
  bound` once binding has run.

### Internal
- `AppContext` gains `first_run`, `paused`, `last_binding_report` and
  the testable helpers `reload_config()`, `config_folder()`,
  `pause_hotkeys()`, `resume_hotkeys()`.
- `BindingReport` (immutable) captures the outcome of the last hotkey
  registration pass; `_bind_shortcuts` writes to it as a side effect.
- 444+ unit tests pass — all `core/` + `ports/` code stays portable
  (no Windows host required). New tests cover the cheat-sheet
  formatter, binding-status formatter, first-run plumbing, reload &
  config-folder lookups, pause/resume idempotency and report
  carry-through, and the prefs reset.

## [0.1.0]

Initial pre-release: see `BRIEF.md` iteration log v1–v4 for the design
that led here.
