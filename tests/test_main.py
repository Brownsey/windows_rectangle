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


def test_parse_args_print_config_path_flag():
    args = _parse_args(["--print-config-path"])
    assert args.print_config_path is True
    assert args.list_shortcuts is False


def test_parse_args_list_shortcuts_flag():
    args = _parse_args(["--list-shortcuts"])
    assert args.list_shortcuts is True


def test_main_print_config_path_short_circuits_before_bind_win32(monkeypatch, capsys):
    """--print-config-path must NOT call bind_win32 — otherwise running it
    while a tray copy is open would either error on the single-instance
    mutex or step on Win32 state."""
    import windows_rectangle.__main__ as m

    def fail_bind(**_):
        raise AssertionError("bind_win32 was called for --print-config-path")

    monkeypatch.setattr(m, "bind_win32", fail_bind)
    rc = m.main(["--print-config-path"])
    assert rc == 0
    out = capsys.readouterr().out
    # Must print something path-shaped.
    assert "config.json" in out


def test_main_check_install_short_circuits_before_bind_win32(monkeypatch, capsys):
    """--check-install must NOT call bind_win32 — running it while a
    tray copy is open shouldn't disturb the running instance."""
    import windows_rectangle.__main__ as m

    def fail_bind(**_):
        raise AssertionError("bind_win32 was called for --check-install")

    monkeypatch.setattr(m, "bind_win32", fail_bind)
    rc = m.main(["--check-install"])
    assert rc in (0, 1)  # depends on whether PySide6 happens to be installed
    out = capsys.readouterr().out
    assert "OVERALL:" in out


def test_main_check_install_json_emits_json(monkeypatch, capsys):
    import windows_rectangle.__main__ as m
    import json as json_mod

    monkeypatch.setattr(m, "bind_win32", lambda **_: (_ for _ in ()).throw(AssertionError()))
    rc = m.main(["--check-install-json"])
    assert rc in (0, 1)
    parsed = json_mod.loads(capsys.readouterr().out)
    assert "version" in parsed


def test_main_list_shortcuts_short_circuits_before_bind_win32(monkeypatch, capsys, tmp_path):
    """--list-shortcuts reads the JSON config, formats via cheat_sheet_text,
    and exits — no Win32 wiring along the way."""
    import windows_rectangle.__main__ as m

    # Point the default JsonConfigStore at a tmp directory so this is
    # isolated from any %APPDATA% the dev machine has.
    monkeypatch.setenv("APPDATA", str(tmp_path))

    def fail_bind(**_):
        raise AssertionError("bind_win32 was called for --list-shortcuts")

    monkeypatch.setattr(m, "bind_win32", fail_bind)
    rc = m.main(["--list-shortcuts"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Left half" in out  # cheat_sheet uses labels from ACTION_LABELS
    assert "ctrl+alt+left" in out  # DEFAULT_SHORTCUTS combo for LEFT_HALF


def test_export_and_import_via_cli_round_trips(monkeypatch, capsys, tmp_path):
    """End-to-end: --export-config writes a file the new machine can
    --import-config into. Both subcommands must short-circuit before
    bind_win32 since they're file-only operations."""
    import windows_rectangle.__main__ as m

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    def fail_bind(**_):
        raise AssertionError("bind_win32 was called for export/import")

    monkeypatch.setattr(m, "bind_win32", fail_bind)

    # Seed an on-disk config by calling load + save through the store
    # the same way --export-config will.
    from windows_rectangle.adapters.json_config import JsonConfigStore
    from windows_rectangle.ports.config_store import Settings

    store = JsonConfigStore()
    store.save(Settings(gap=33))

    snapshot = tmp_path / "snap.json"
    rc = m.main(["--export-config", str(snapshot)])
    assert rc == 0
    assert snapshot.exists()
    assert "exported settings to" in capsys.readouterr().out

    # Move "appdata" out of the way to simulate a fresh machine.
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata2"))
    rc = m.main(["--import-config", str(snapshot)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "imported settings from" in out
    # Verify the new config was actually persisted.
    new_store = JsonConfigStore()
    assert new_store.load().gap == 33


def test_import_missing_file_returns_1(monkeypatch, capsys, tmp_path):
    import windows_rectangle.__main__ as m

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(m, "bind_win32", lambda **_: (_ for _ in ()).throw(AssertionError()))
    rc = m.main(["--import-config", str(tmp_path / "nope.json")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "import failed" in err


def test_import_bad_json_returns_1(monkeypatch, capsys, tmp_path):
    import windows_rectangle.__main__ as m

    bad = tmp_path / "bad.json"
    bad.write_text("not { json", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(m, "bind_win32", lambda **_: (_ for _ in ()).throw(AssertionError()))
    rc = m.main(["--import-config", str(bad)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not valid JSON" in err


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
