# Windows Rectangle architecture

Windows Rectangle is a Windows 10/11 tray utility written in Python 3.11+.
Its geometry and shortcut conventions are inspired by Rectangle. Attribution
is retained in the root THIRD_PARTY_NOTICES.md; upstream source is not bundled.

## Runtime boundaries

All application code lives in `apps/windows/windows_rectangle`; tests live in
`apps/windows/tests`. The root pyproject.toml selects those paths for both
packaging and pytest.

- `core/` contains window geometry, actions, cycling, undo, monitor selection,
  snapping and workspace matching. It does not import Win32 or Qt.
- `ports/` describes the window manager, hotkeys, configuration, startup and
  single-instance boundaries.
- `adapters/` implements those boundaries using ctypes, Win32 and atomic JSON
  files. Native function signatures explicitly describe pointer-sized handles.
- `ui/` contains lazily imported PySide6 tray, preferences, overlay and workspace
  editor components.
- `app.py` owns application state, native lifecycle and dispatch.
- `__main__.py` owns command-line diagnostics and the Qt/headless event loop.

## Input and movement

Global shortcuts run on a native message-pump thread. Callbacks enqueue actions;
the main thread dispatches a bounded batch on its next timer tick. A bounded queue
prevents unbounded memory growth, and newly submitted actions wait for a later
batch. Workspace restores process one request per tick.

The low-level mouse hook only publishes the latest immutable input snapshot.
It performs no window enumeration, DWM queries, geometry, logging or movement.
The main timer checks Windows' native move/size loop, captures the moved HWND,
and rejects content dragging, resize operations and cancelled moves. Snap release
uses the latest cursor coordinates and exact target rectangle, without shortcut
cycling or foreground-window reselection. Very short clicks entirely between
timer ticks do not create a snap session.

Win32 coordinates use physical pixels. Visible DWM frame bounds exclude invisible
resize borders; placement expands them back to outer window bounds. The overlay
must use the same physical coordinates, including on scaled monitors. Native moves
use asynchronous SetWindowPos so another application's message loop cannot block
the UI indefinitely. A successful call means Windows accepted the request; an
application may still enforce its own minimum size or position rules.

## Settings and workspaces

Settings live at `%APPDATA%\windows_rectangle\config.json`. Saves write, flush,
and atomically replace a temporary file in the same directory. Malformed startup
configuration is preserved and logged; invalid imports do not overwrite settings.

Workspace rules match process names, title text or regular expressions. Matching
is deterministic and one-to-one, prioritizing more specific rules. Positions use
integer basis points so saved layouts scale across work-area sizes. Editors merge
the fields they own into the current settings before persisting; unrelated live
preferences must survive an autosave.

## Lifecycle

The single-instance mutex is acquired before configuration writes or native
threads are created. Startup failures unwind acquired resources. Quit unregisters
hotkeys, unhooks the mouse, joins message pumps and releases the mutex. Closing a
dialog leaves the tray app running. Pausing shortcuts persists through settings
changes until the user resumes them.

## Verification and distribution

Run `scripts/check.ps1` for Ruff lint, formatting, strict core typing and pytest.
The Windows CI workflow uses the same command. Tests include deterministic native
boundary failures and Qt widget interactions; hardware-specific scenarios remain
separate evidence, as recorded in the root REVIEW.md.

`windows_rectangle.spec` is the single PyInstaller configuration. Both build
launchers route through `scripts/build-windows.ps1`. Builds use a portable directory
with Qt exclusions, logos and attribution; startup does not unpack a one-file
archive. The release script checks the executable with `--check-install`, then
produces a ZIP and SHA-256 checksums under `apps/windows/exe`.

## Performance principles

Keep idle work constant and avoid native calls when no drag is active. Coalesce
mouse movement instead of accumulating it. Cache within a single operation only
where lifetime is known; do not persist HWND, monitor or process-name caches across
operations because windows can close, handles can be reused and monitors can change.
Measure improvements against representative input before adding concurrency,
frameworks or persistent caches. See REVIEW.md for measured results and limits.
