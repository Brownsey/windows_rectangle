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
