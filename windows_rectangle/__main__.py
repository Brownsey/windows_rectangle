"""`python -m windows_rectangle` — the runtime entrypoint.

Tries Qt (PySide6) for the proper tray+prefs experience. Falls back to
a headless stdlib-only runner (hotkeys + dispatcher, no UI) when Qt
isn't installed — useful for smoke-testing the dispatcher on a fresh
clone without the heavyweight Qt dependency.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from . import __version__
from .app import SecondInstanceError, bind_win32


_log = logging.getLogger("windows_rectangle")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="windows_rectangle")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument(
        "--headless",
        action="store_true",
        help="run without Qt — hotkeys + dispatcher only, no tray UI",
    )
    p.add_argument(
        "--command-line",
        default=None,
        help="full command line used for the launch-at-login registry entry",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args(argv)


def _setup_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def _run_headless(ctx) -> int:
    """Stdlib-only main loop: drain the ActionBus on a ~60 Hz schedule.

    Exits cleanly on SIGINT.
    """
    stop = False

    def _on_sig(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _on_sig)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _on_sig)
        except ValueError:
            pass  # not main thread

    _log.info("running headless — Ctrl+C to exit")
    while not stop:
        ctx.drain_actions()
        time.sleep(1.0 / 60)
    return 0


def _run_qt(ctx) -> int:
    """Qt loop with a 16ms QTimer that drains the ActionBus on the GUI thread."""
    from PySide6 import QtCore, QtWidgets

    from .ui.tray import install as install_tray

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    # The tray is the visible-anywhere control surface; on quit it calls
    # QApplication.quit() which unwinds the event loop.
    tray = install_tray(ctx)
    _log.info("tray installed")
    # Keep a strong reference on the QApplication so it lives as long as the loop.
    app._tray = tray  # type: ignore[attr-defined]

    timer = QtCore.QTimer()
    timer.setInterval(16)  # ~60 Hz; brief §5 #7 mouse-snap throttle target
    timer.timeout.connect(ctx.drain_actions)
    timer.start()
    rc = app.exec()
    timer.stop()
    return rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(args.log_level)

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
