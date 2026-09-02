"""Rotating-file logging support.

The tray is a long-running daemon; without on-disk logs a user reporting
a bug has nothing to attach. This module wires a `RotatingFileHandler`
onto the root logger writing to
`%APPDATA%\\windows_rectangle\\windows_rectangle.log`, capped at 1 MB
with 3 historical backups (so total ≤ 4 MB).

Importable on any platform — the path falls back to
`~/.windows_rectangle/windows_rectangle.log` off Windows so tests can
drive it without env-hacking.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_BYTES = 1_000_000
DEFAULT_LOG_BACKUPS = 3
LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def default_log_path() -> Path:
    """Resolve `%APPDATA%/windows_rectangle/windows_rectangle.log`.

    Mirrors `json_config.default_config_path()` so the log lives next to
    the config — one folder for "Open config folder…" and "Open log
    file…" to converge on.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "windows_rectangle" / "windows_rectangle.log"
    return Path.home() / ".windows_rectangle" / "windows_rectangle.log"


def install_file_handler(
    *,
    path: Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = DEFAULT_LOG_BYTES,
    backups: int = DEFAULT_LOG_BACKUPS,
) -> Path | None:
    """Attach a `RotatingFileHandler` to the root logger.

    Returns the path of the active log file, or None on failure (e.g.
    parent directory not writable). Failures are silent — losing on-
    disk logging must never block the tray from starting.

    Idempotent: if a `RotatingFileHandler` is already attached to the
    same file the call is a no-op (so tests / repeat startup paths
    don't double-up handlers and write each line twice).
    """
    target = (path or default_log_path()).expanduser().resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    root = logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, RotatingFileHandler):
            # Compare resolved paths so a relative-vs-absolute mismatch
            # doesn't accidentally re-add a sibling handler.
            try:
                if Path(existing.baseFilename).resolve() == target:
                    return target
            except OSError:
                continue

    try:
        handler = RotatingFileHandler(
            str(target),
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
            delay=True,  # don't open until first emit — cheap import
        )
    except OSError:
        return None
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    # Don't override root level here — the CLI's --log-level controls
    # that; we just want the handler to respect its own minimum.
    return target
