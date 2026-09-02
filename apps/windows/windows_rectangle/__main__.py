"""`python -m windows_rectangle` — the runtime entrypoint.

Tries Qt (PySide6) for the proper tray+prefs experience. Falls back to
a headless stdlib-only runner (hotkeys + dispatcher, no UI) when Qt
isn't installed — useful for smoke-testing the dispatcher on a fresh
clone without the heavyweight Qt dependency.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .app import SecondInstanceError, bind_win32

_log = logging.getLogger("windows_rectangle")


_EPILOG = """\
examples:
  windows_rectangle                        run the tray app
  windows_rectangle --open-preferences     run the tray app and open Preferences
  windows_rectangle --headless             run without Qt (hotkeys only)
  windows_rectangle --check-install        verify the install
  windows_rectangle --list-shortcuts       print current shortcuts
  windows_rectangle --print-monitors       dump monitor geometry
  windows_rectangle --export-config s.json snapshot settings to s.json
  windows_rectangle --import-config s.json restore settings from s.json

The "informational" flags short-circuit before any Win32 wiring or the
single-instance mutex, so they're safe to run while another tray copy
is already open.
"""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="windows_rectangle",
        description="Rectangle-for-Windows window manager.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=__version__)

    runtime = p.add_argument_group("runtime")
    runtime.add_argument(
        "--headless",
        action="store_true",
        help="run without Qt - hotkeys + dispatcher only, no tray UI",
    )
    runtime.add_argument(
        "--open-preferences",
        action="store_true",
        help="open Preferences after starting the tray app",
    )
    runtime.add_argument(
        "--tray",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    runtime.add_argument(
        "--command-line",
        default=None,
        help="full command line used for the launch-at-login registry entry",
    )
    runtime.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="root logger threshold (default: INFO)",
    )

    info = p.add_argument_group(
        "informational",
        description=(
            "These flags print state and exit. They do NOT start the tray, "
            "take the single-instance mutex, or install hotkeys - safe to "
            "run while another copy is active."
        ),
    )
    info.add_argument(
        "--print-config-path",
        action="store_true",
        help="print the on-disk config path",
    )
    info.add_argument(
        "--list-shortcuts",
        action="store_true",
        help="print every action and its currently-configured shortcut",
    )
    info.add_argument(
        "--check-install",
        action="store_true",
        help="self-diagnostic; exits 0 when every required check passed",
    )
    info.add_argument(
        "--check-install-json",
        action="store_true",
        help="like --check-install but emit machine-readable JSON",
    )
    info.add_argument(
        "--print-monitors",
        action="store_true",
        help="dump monitor bounds + work_area + primary flag (Windows only)",
    )
    info.add_argument(
        "--print-monitors-json",
        action="store_true",
        help="like --print-monitors but emit machine-readable JSON",
    )

    migration = p.add_argument_group(
        "migration",
        description="Backup + restore settings for cross-machine moves.",
    )
    migration.add_argument(
        "--export-config",
        metavar="PATH",
        default=None,
        help="snapshot the current config to PATH and exit",
    )
    migration.add_argument(
        "--import-config",
        metavar="PATH",
        default=None,
        help="load settings from PATH, persist to the user config, and exit",
    )
    migration.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "with --import-config: show what would change but don't write. "
            "Lets a user preview a snapshot before committing."
        ),
    )
    args = p.parse_args(argv)

    # Mutual exclusion: --export-config and --import-config don't make
    # sense in the same call; argparse can't model this cleanly because
    # both take a value rather than store_true.
    if args.export_config is not None and args.import_config is not None:
        p.error("--export-config and --import-config are mutually exclusive")
    if args.dry_run and args.import_config is None:
        p.error("--dry-run requires --import-config")

    return args


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Best-effort rotating file handler under %APPDATA% — survives a
    # crash so users can attach the log to bug reports. Failures (e.g.
    # locked-down %APPDATA%) are silent: console logging still works.
    from .log_file import install_file_handler

    install_file_handler(level=level)


def _default_command_line() -> str:
    """Return the source or packaged command used by Launch at login."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable, "--tray"])
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    source_root = str(Path(__file__).resolve().parents[1])
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0,{source_root!r});"
        "sys.argv=['windows_rectangle','--tray'];"
        "runpy.run_module('windows_rectangle',run_name='__main__')"
    )
    return subprocess.list2cmdline([pythonw, "-c", bootstrap])


def _show_tray_message(tray_controller, title: str, body: str) -> None:
    icon = getattr(tray_controller, "icon", None)
    if icon is not None:
        icon.showMessage(title, body)


def _activate_existing_preferences() -> bool:
    """Show the resident instance's hidden Preferences window on Windows."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    window = user32.FindWindowW(None, "Windows Rectangle")
    if not window:
        return False
    user32.ShowWindow(window, 9)  # SW_RESTORE also reveals a hidden Qt window.
    user32.SetForegroundWindow(window)
    return True


def _run_headless(ctx) -> int:
    """Stdlib-only main loop: drain the ActionBus on a ~60 Hz schedule.

    Exits cleanly on SIGINT.
    """
    stop = False

    def _on_sig(*_):
        nonlocal stop
        stop = True

    import contextlib

    signal.signal(signal.SIGINT, _on_sig)
    if hasattr(signal, "SIGTERM"):
        with contextlib.suppress(ValueError):
            signal.signal(signal.SIGTERM, _on_sig)  # ValueError off main thread

    _log.info("running headless — Ctrl+C to exit")
    # No overlay to repaint in headless mode, so 60 Hz is wasteful.
    # 30 Hz keeps hotkey latency under ~33 ms (still imperceptible) and
    # halves CPU usage while idle.
    HEADLESS_POLL_HZ = 30
    period = 1.0 / HEADLESS_POLL_HZ
    while not stop:
        ctx.drain_actions()
        ctx.maintenance()
        time.sleep(period)
    return 0


def _run_qt(ctx, *, open_preferences: bool = False) -> int:
    """Qt loop with a 16ms QTimer that drains the ActionBus + drag preview.

    Single Qt event loop, single drain timer (brief §5 #8 "competing event
    loops"). The mouse hook + hotkey pump each have their own daemon
    Win32 message loops; both marshal back here via ActionBus/LatestValue.
    """
    from PySide6 import QtCore, QtGui, QtWidgets

    from .ui.logo import build_tray_qicon
    from .ui.overlay import OverlayController
    from .ui.overlay import hide as overlay_hide
    from .ui.overlay import install as install_overlay
    from .ui.overlay import show_for as overlay_show_for
    from .ui.preferences import show as show_preferences
    from .ui.tray import install as install_tray
    from .ui.tray import workspace_result_text

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(build_tray_qicon(QtGui))
    app.setQuitOnLastWindowClosed(False)
    # The tray is the visible-anywhere control surface; on quit it calls
    # QApplication.quit() which unwinds the event loop.

    def _open_prefs() -> None:
        try:
            show_preferences(ctx)
        except Exception:  # noqa: BLE001
            _log.exception("preferences dialog failed")

    tray = install_tray(ctx, on_open_preferences=_open_prefs)
    _log.info("tray installed")
    if open_preferences:
        QtCore.QTimer.singleShot(0, _open_prefs)
    elif hasattr(ctx, "settings"):
        # Create the native window handle without painting it. A later
        # `--open-preferences` process can then find and reveal this window.
        try:
            controller = show_preferences(ctx)
            controller.window.hide()
        except Exception:  # noqa: BLE001
            _log.exception("could not prepare hidden preferences window")

    def _on_workspace_result(workspace_id, result, error: str) -> None:
        summary = ""
        if error:
            _show_tray_message(tray, "Layout failed", error)
            summary = f"Layout failed: {error}"
        elif result is not None:
            summary = workspace_result_text(result)
            _show_tray_message(tray, "Layout ready", summary)
        dialog = getattr(app, "_windows_rectangle_workspaces", None)
        if dialog is None or getattr(dialog, "selected_id", None) != workspace_id:
            return
        dialog.status.setText(summary)
        has_problem = bool(error) or (
            result is not None and any(item.status != "moved" for item in result.placements)
        )
        state = "error" if error else "warning" if has_problem else "saved"
        dialog.status.setProperty("status", state)
        dialog.status.style().unpolish(dialog.status)
        dialog.status.style().polish(dialog.status)

    # Snap-preview overlay (frameless translucent click-through, brief §3).
    overlay: OverlayController | None = None
    try:
        overlay = install_overlay()
        _log.info("snap-preview overlay installed")
    except Exception:  # noqa: BLE001 — overlay is non-essential
        _log.warning("snap-preview overlay install failed", exc_info=True)

    # Keep strong refs on the QApplication so they live as long as the loop.
    app._tray = tray  # type: ignore[attr-defined]
    app._overlay = overlay  # type: ignore[attr-defined]

    # Hoist the overlay show/hide closures so they aren't reallocated
    # 60×/sec on the Qt timer. (drain_drag_preview already dedups so they
    # rarely actually fire, but the lambda creation happens every tick.)
    if overlay is not None:

        def _on_show(rect) -> None:
            overlay_show_for(overlay, rect)

        def _on_hide() -> None:
            overlay_hide(overlay)
    else:
        _on_show = _on_hide = None  # type: ignore[assignment]

    def _tick() -> None:
        ctx.drain_actions()
        ctx.drain_workspace_results(_on_workspace_result)
        if overlay is not None:
            ctx.drain_drag_preview(on_show=_on_show, on_hide=_on_hide)
        ctx.maintenance()  # rate-limited cycle/history prune (brief §5 #9)

    timer = QtCore.QTimer()
    timer.setInterval(16)  # ~60 Hz; brief §5 #7 mouse-snap throttle target
    timer.timeout.connect(_tick)
    timer.start()
    rc = app.exec()
    timer.stop()
    return rc


def _run_informational(args: argparse.Namespace) -> int:
    """Handle the no-side-effect informational subcommands.

    `--print-config-path` and `--list-shortcuts` are intentionally
    importable on any platform (no Win32 adapter needed) so a user
    can shell-script them or run from CI. Returns the exit code, or
    -1 if no informational flag was passed.
    """
    if args.print_config_path:
        from .adapters.json_config import default_config_path

        print(default_config_path())
        return 0

    if args.list_shortcuts:
        from .adapters.json_config import JsonConfigStore
        from .ui.cheat_sheet import cheat_sheet_text

        store = JsonConfigStore()
        settings = store.load()
        print(cheat_sheet_text(settings.shortcuts))
        return 0

    if args.check_install or args.check_install_json:
        from .diagnostics import run_check_install

        return run_check_install(json_output=args.check_install_json)

    if args.export_config is not None:
        from .adapters.json_config import JsonConfigStore

        store = JsonConfigStore()
        dest = store.export_to(args.export_config)
        print(f"exported settings to: {dest}")
        return 0

    if args.import_config is not None:
        from .adapters.json_config import JsonConfigStore

        store = JsonConfigStore()
        try:
            incoming = JsonConfigStore.parse_path(args.import_config)
        except FileNotFoundError as e:
            print(f"import failed: {e}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as e:
            print(f"import failed: {args.import_config} is not valid JSON ({e})", file=sys.stderr)
            return 1

        if args.dry_run:
            # Dry run: show the per-field changes without touching disk.
            from .settings_diff import diff_settings

            current = store.load()
            lines = diff_settings(current, incoming)
            print(f"dry-run: would import from {args.import_config}")
            print(f"would write to: {store.path}")
            if not lines:
                print("(no changes — incoming settings match current)")
            else:
                print("changes:")
                for line in lines:
                    print(line)
            return 0

        store.save(incoming)
        print(f"imported settings from: {args.import_config}")
        print(f"saved to: {store.path}")
        return 0

    if args.print_monitors or args.print_monitors_json:
        # Lazy import: Win32WindowManager is Windows-only; the formatter
        # is portable so an off-Windows host gets a clear error rather
        # than an ImportError mid-print.
        from .monitors_view import monitors_to_json, monitors_to_text

        try:
            from .adapters.win32_windows import Win32WindowManager
        except ImportError:
            print(
                "--print-monitors requires Windows (pywin32). "
                "Run on a Windows host or in a Win32 venv.",
                file=sys.stderr,
            )
            return 1

        try:
            wm = Win32WindowManager()
            monitors = wm.list_monitors()
        except Exception as e:  # noqa: BLE001 — surface as exit code 1
            print(f"failed to enumerate monitors: {e}", file=sys.stderr)
            return 1

        if args.print_monitors_json:
            print(monitors_to_json(monitors))
        else:
            print(monitors_to_text(monitors))
        return 0

    return -1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(args.log_level)
    packaged_default = bool(getattr(sys, "frozen", False) and not args.tray and not args.headless)
    wants_preferences = bool(args.open_preferences or packaged_default)

    info_rc = _run_informational(args)
    if info_rc != -1:
        return info_rc

    try:
        ctx = bind_win32(command_line=args.command_line or _default_command_line())
    except SecondInstanceError:
        if wants_preferences and _activate_existing_preferences():
            _log.info("activated Preferences in the running instance")
            return 0
        _log.warning("another instance is already running — exiting")
        return 0
    except RuntimeError as e:
        # Win32 adapters refuse to construct off-Windows.
        _log.error("startup failed: %s", e)
        return 1

    try:
        if args.headless:
            return _run_headless(ctx)
        try:
            return _run_qt(ctx, open_preferences=wants_preferences)
        except ImportError:
            _log.warning("PySide6 not installed — falling back to --headless")
            return _run_headless(ctx)
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    sys.exit(main())
