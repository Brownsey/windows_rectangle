"""Runtime entry point for `python -m windows_rectangle`.

The normal Windows path uses Qt for the tray icon and preferences window.
Headless mode exists for smoke tests and environments without a desktop UI.
"""

from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import sys
import time
from contextlib import suppress

from . import __version__
from .app import SecondInstanceError, bind_win32

_log = logging.getLogger("windows_rectangle")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="windows_rectangle")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run without Qt: hotkeys and dispatcher only, no tray UI",
    )
    parser.add_argument(
        "--open-preferences",
        "--preferences",
        dest="open_preferences",
        action="store_true",
        help="show the shortcut/preferences window on startup",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="start tray-only without opening the preferences window",
    )
    parser.add_argument(
        "--command-line",
        default=None,
        help="full command line used for the launch-at-login registry entry",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)
    if args.headless and args.open_preferences:
        parser.error("--open-preferences cannot be used with --headless")
    if args.headless and args.tray:
        parser.error("--tray cannot be used with --headless")
    if args.tray and args.open_preferences:
        parser.error("--tray cannot be used with --open-preferences")
    return args


def _setup_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def _default_autostart_command_line() -> str:
    """Build a tray-only command for the current runtime environment."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable, "--tray"])
    return subprocess.list2cmdline([sys.executable, "-m", "windows_rectangle", "--tray"])


def _should_open_preferences(args: argparse.Namespace) -> bool:
    if args.open_preferences:
        return True
    return bool(getattr(sys, "frozen", False)) and not args.tray


def _run_headless(ctx) -> int:
    """Drain the ActionBus on a 60 Hz loop without showing Qt UI."""
    stop = False

    def _on_sig(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _on_sig)
    if hasattr(signal, "SIGTERM"):
        with suppress(ValueError):
            signal.signal(signal.SIGTERM, _on_sig)

    _log.info("running headless; Ctrl+C to exit")
    while not stop:
        ctx.drain_actions()
        time.sleep(1.0 / 60)
    return 0


def _run_qt(ctx, *, open_preferences: bool = False) -> int:
    """Run the Qt tray app and optionally show Preferences on startup."""
    from PySide6 import QtCore, QtWidgets

    from .ui.preferences import show as show_preferences
    from .ui.tray import install as install_tray

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = install_tray(ctx, on_open_preferences=lambda: show_preferences(ctx))
    _log.info("tray installed")
    app._tray = tray  # type: ignore[attr-defined]

    if open_preferences:
        show_preferences(ctx)

    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.PreciseTimer)
    timer.setInterval(16)
    timer.timeout.connect(ctx.drain_actions)
    timer.start()
    rc = app.exec()
    timer.stop()
    return rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(args.log_level)

    try:
        ctx = bind_win32(command_line=args.command_line or _default_autostart_command_line())
    except SecondInstanceError:
        _log.warning("another instance is already running; exiting")
        return 0
    except RuntimeError as exc:
        _log.error("startup failed: %s", exc)
        return 1

    try:
        if args.headless:
            return _run_headless(ctx)
        try:
            return _run_qt(ctx, open_preferences=_should_open_preferences(args))
        except ImportError:
            _log.warning("PySide6 not installed; falling back to --headless")
            return _run_headless(ctx)
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    sys.exit(main())
