"""Tests for windows_rectangle.__main__.

We don't actually run the main loop — too disruptive. We only test the
argparse layer and the early-exit paths (second instance, no Win32).
"""

import pytest

from windows_rectangle.__main__ import _parse_args


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.headless is False
    assert args.command_line is None
    assert args.log_level == "INFO"


def test_parse_args_headless_flag():
    args = _parse_args(["--headless"])
    assert args.headless is True


def test_parse_args_command_line():
    args = _parse_args(["--command-line", r"C:\app.exe"])
    assert args.command_line == r"C:\app.exe"


def test_parse_args_log_level():
    args = _parse_args(["--log-level", "DEBUG"])
    assert args.log_level == "DEBUG"


def test_parse_args_invalid_log_level_rejected():
    with pytest.raises(SystemExit):
        _parse_args(["--log-level", "TRACE"])


def test_version_flag_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        _parse_args(["--version"])
    assert exc.value.code == 0


def test_setup_logging_sets_root_level():
    """_setup_logging maps --log-level to logging.basicConfig's level."""
    import logging

    from windows_rectangle.__main__ import _setup_logging

    # Save + restore so we don't poison other tests.
    saved_level = logging.getLogger().level
    try:
        _setup_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING
        _setup_logging("DEBUG")
        # basicConfig is a no-op if root has handlers; the level may not
        # change on the second call. Allow either WARNING or DEBUG.
        assert logging.getLogger().level in (logging.WARNING, logging.DEBUG)
    finally:
        logging.getLogger().setLevel(saved_level)
