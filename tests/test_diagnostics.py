"""Tests for windows_rectangle.diagnostics — the --check-install backend.

Pure-Python; no Win32, no Qt, no actual binding. The diagnostic only
imports module names + checks one path — everything else is structural.
"""

from __future__ import annotations

import json
from pathlib import Path

from windows_rectangle import __version__
from windows_rectangle.diagnostics import (
    DiagnosticReport,
    ImportCheck,
    collect_diagnostic_report,
    run_check_install,
)


def _all_ok(checks):
    return all(c.importable for c in checks)


def test_report_has_required_core_modules(tmp_path):
    """Every shipped package module (core, adapters.json_config, app)
    must be importable; if not, the build is broken."""
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    assert rep.version == __version__
    required_names = {c.name for c in rep.required}
    # Pin the *names* that gate the OK status — guarding against an
    # accidental delete of an entry in collect_diagnostic_report.
    assert "windows_rectangle.core.actions" in required_names
    assert "windows_rectangle.core.dispatcher" in required_names
    assert "windows_rectangle.app" in required_names
    assert "windows_rectangle.adapters.json_config" in required_names
    assert _all_ok(rep.required)


def test_optional_pyside6_skipped_off_windows(tmp_path):
    """PySide6 may not be installed in CI; that's fine for `ok`."""
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    assert any(c.name == "PySide6" for c in rep.optional)
    # ok ignores optional checks.
    assert rep.ok is True


def test_windows_path_appends_win32api(tmp_path):
    rep = collect_diagnostic_report(
        on_windows=True,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    optional_names = {c.name for c in rep.optional}
    assert "win32api" in optional_names


def test_config_exists_reflects_filesystem(tmp_path):
    real = tmp_path / "config.json"
    real.write_text("{}", encoding="utf-8")
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: real,
    )
    assert rep.config_exists is True
    assert rep.config_path == str(real)


def test_config_missing_path_is_not_a_failure(tmp_path):
    """Fresh installs have no config until the user opens prefs — that
    must not be a `--check-install` failure."""
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "never_made.json",
    )
    assert rep.config_exists is False
    assert rep.ok is True


def test_to_text_mentions_overall_status(tmp_path):
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    out = rep.to_text()
    assert "OVERALL: OK" in out
    assert rep.version in out


def test_to_json_round_trips(tmp_path):
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    parsed = json.loads(rep.to_json())
    assert parsed["version"] == rep.version
    # required list serialises ImportCheck → dict.
    assert isinstance(parsed["required"], list)
    assert parsed["required"][0]["name"].startswith("windows_rectangle.")


def test_failing_required_check_flips_ok(monkeypatch, tmp_path):
    """Force a required-import failure and prove ok goes False."""
    from windows_rectangle import diagnostics as d

    real_check = d._check

    def stub(name: str) -> ImportCheck:
        if name == "windows_rectangle.app":
            return ImportCheck(name=name, importable=False, detail="forced")
        return real_check(name)

    monkeypatch.setattr(d, "_check", stub)
    rep = collect_diagnostic_report(
        on_windows=False,
        config_path_factory=lambda: tmp_path / "no_config.json",
    )
    assert rep.ok is False
    # to_text shows the FAIL marker for the failing check.
    out = rep.to_text()
    assert "[FAIL] windows_rectangle.app" in out
    assert "OVERALL: FAIL" in out


def test_run_check_install_returns_0_when_ok(monkeypatch, capsys, tmp_path):
    """The CLI front door: exit code 0 on a clean run, prints text."""
    from windows_rectangle import diagnostics as d

    monkeypatch.setattr(
        d,
        "collect_diagnostic_report",
        lambda **kw: DiagnosticReport(
            version="0.x", python="3.13", platform="test",
            required=[ImportCheck(name="x", importable=True)],
            optional=[],
            config_path=str(tmp_path / "c.json"),
            config_exists=False,
        ),
    )
    rc = run_check_install()
    assert rc == 0
    assert "OVERALL: OK" in capsys.readouterr().out


def test_run_check_install_returns_1_on_failure(monkeypatch, capsys, tmp_path):
    from windows_rectangle import diagnostics as d

    monkeypatch.setattr(
        d,
        "collect_diagnostic_report",
        lambda **kw: DiagnosticReport(
            version="0.x", python="3.13", platform="test",
            required=[ImportCheck(name="x", importable=False, detail="boom")],
            optional=[],
            config_path=str(tmp_path / "c.json"),
            config_exists=False,
        ),
    )
    rc = run_check_install()
    assert rc == 1


def test_run_check_install_json_emits_parseable_json(monkeypatch, capsys, tmp_path):
    from windows_rectangle import diagnostics as d

    monkeypatch.setattr(
        d,
        "collect_diagnostic_report",
        lambda **kw: DiagnosticReport(
            version="0.x", python="3.13", platform="test",
            required=[ImportCheck(name="x", importable=True)],
            optional=[],
            config_path=str(tmp_path / "c.json"),
            config_exists=False,
        ),
    )
    rc = run_check_install(json_output=True)
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["version"] == "0.x"
