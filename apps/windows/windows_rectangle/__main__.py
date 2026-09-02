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
import sys
import time

from . import __version__
from .app import SecondInstanceError, bind_win32

_log = logging.getLogger("windows_rectangle")


_EPILOG = """\
examples:
  windows_rectangle                        run the tray app
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


def _run_qt(ctx) -> int:
    """Qt loop with a 16ms QTimer that drains the ActionBus + drag preview.

    Single Qt event loop, single drain timer (brief §5 #8 "competing event
    loops"). The mouse hook + hotkey pump each have their own daemon
    Win32 message loops; both marshal back here via ActionBus/LatestValue.
    """
    from PySide6 import QtCore, QtWidgets

    from .ui.overlay import OverlayController
    from .ui.overlay import hide as overlay_hide
    from .ui.overlay import install as install_overlay
    from .ui.overlay import show_for as overlay_show_for
    from .ui.preferences import open_prefs_window
    from .ui.prefs_dialog import build_dialog as build_prefs_dialog
    from .ui.tray import install as install_tray

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # The tray is the visible-anywhere control surface; on quit it calls
    # QApplication.quit() which unwinds the event loop.

    def _open_prefs() -> None:
        try:
            open_prefs_window(ctx, dialog_factory=build_prefs_dialog)
        except Exception:  # noqa: BLE001
            _log.exception("preferences dialog failed")

    tray = install_tray(ctx, on_open_preferences=_open_prefs)
    _log.info("tray installed")
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

    info_rc = _run_informational(args)
    if info_rc != -1:
        return info_rc

    try:
        ctx = bind_win32(command_line=args.command_line)
    except SecondInstanceError:
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
            return _run_qt(ctx)
        except ImportError:
            _log.warning("PySide6 not installed — falling back to --headless")
            return _run_headless(ctx)
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    sys.exit(main())
