"""Tests for windows_rectangle.log_file — rotating-file logging setup.

Pure stdlib — verifies the handler attaches once, respects max bytes,
and degrades gracefully when the parent directory can't be created.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from windows_rectangle.log_file import (
    DEFAULT_LOG_BACKUPS,
    DEFAULT_LOG_BYTES,
    default_log_path,
    install_file_handler,
)


@pytest.fixture(autouse=True)
def _strip_root_handlers():
    """Test isolation: the root logger leaks handlers between tests
    if we don't reset. Snapshot + restore so other test modules that
    rely on default logging stay green."""
    root = logging.getLogger()
    saved = list(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in saved:
            root.removeHandler(h)


def test_default_log_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = default_log_path()
    assert p.parent.name == "windows_rectangle"
    assert p.name == "windows_rectangle.log"
    assert str(p).startswith(str(tmp_path))


def test_default_log_path_falls_back_off_windows(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    p = default_log_path()
    assert p.name == "windows_rectangle.log"
    assert ".windows_rectangle" in p.parts


def test_install_file_handler_attaches_rotating_handler(tmp_path):
    target = tmp_path / "windows_rectangle.log"
    out = install_file_handler(path=target)
    assert out == target.resolve()

    root = logging.getLogger()
    matches = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert any(Path(h.baseFilename).resolve() == target.resolve() for h in matches)


def test_install_file_handler_is_idempotent(tmp_path):
    target = tmp_path / "windows_rectangle.log"
    install_file_handler(path=target)
    install_file_handler(path=target)

    root = logging.getLogger()
    matches = [
        h for h in root.handlers
        if isinstance(h, RotatingFileHandler)
        and Path(h.baseFilename).resolve() == target.resolve()
    ]
    assert len(matches) == 1, "duplicate handler attached"


def test_install_writes_log_line_to_disk(tmp_path):
    target = tmp_path / "windows_rectangle.log"
    install_file_handler(path=target, level=logging.INFO)

    logger = logging.getLogger("windows_rectangle.test_log_file")
    logger.setLevel(logging.INFO)
    logger.info("hello world from a test")

    # delay=True means the file appears only after first emit.
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "hello world from a test" in content


def test_install_returns_none_when_parent_unmakeable(tmp_path, monkeypatch):
    """A file existing where the parent dir should be should make
    mkdir fail. We use a real file at the intended parent path."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    target = blocker / "windows_rectangle.log"  # blocker is a FILE
    out = install_file_handler(path=target)
    assert out is None


def test_rotation_limits_are_threaded_through(tmp_path):
    """Constructor args reach the handler — otherwise a quick infinite
    error loop would grow the log without bound."""
    target = tmp_path / "windows_rectangle.log"
    install_file_handler(path=target, max_bytes=1234, backups=2)
    root = logging.getLogger()
    h = next(
        h for h in root.handlers
        if isinstance(h, RotatingFileHandler)
        and Path(h.baseFilename).resolve() == target.resolve()
    )
    assert h.maxBytes == 1234
    assert h.backupCount == 2


def test_defaults_keep_log_under_four_megabytes():
    """1 MB × 4 generations (current + 3 backups) is the documented cap.
    Lock in the defaults so a reckless edit doesn't ship a 100 MB log."""
    assert DEFAULT_LOG_BYTES == 1_000_000
    assert DEFAULT_LOG_BACKUPS == 3
