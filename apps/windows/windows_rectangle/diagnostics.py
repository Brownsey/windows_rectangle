"""Self-diagnostic for the install — driven by the `--check-install`
CLI subcommand.

Importable on any platform; the Windows-specific probes degrade
gracefully off Windows so the same code is testable in CI. Returns a
structured `DiagnosticReport` so callers can serialise to JSON or print
human-readable.

This module is intentionally cheap to import: it does NOT touch Win32
state, does NOT take the single-instance mutex, and does NOT install
hotkeys. Safe to run with another tray copy live.
"""

from __future__ import annotations

import importlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import __version__


@dataclass(slots=True)
class ImportCheck:
    """Result of probing one module by name."""

    name: str
    importable: bool
    detail: str = ""


@dataclass(slots=True)
class DiagnosticReport:
    """Outcome of a `--check-install` run.

    `ok` is True iff every required check passed. Optional probes
    (e.g. pywin32 on a non-Windows host) don't gate it.
    """

    version: str
    python: str
    platform: str
    required: list[ImportCheck] = field(default_factory=list)
    optional: list[ImportCheck] = field(default_factory=list)
    config_path: str = ""
    config_exists: bool = False

    @property
    def ok(self) -> bool:
        return all(c.importable for c in self.required)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(asdict(self), indent=indent, sort_keys=True)

    def to_text(self) -> str:
        lines: list[str] = [
            f"Windows Rectangle {self.version}",
            f"  python:   {self.python}",
            f"  platform: {self.platform}",
            "",
            "Required:",
        ]
        for c in self.required:
            mark = "OK " if c.importable else "FAIL"
            lines.append(f"  [{mark}] {c.name}{('  - ' + c.detail) if c.detail else ''}")
        if self.optional:
            lines.append("")
            lines.append("Optional:")
            for c in self.optional:
                mark = "OK " if c.importable else "--"
                lines.append(f"  [{mark}] {c.name}{('  - ' + c.detail) if c.detail else ''}")
        lines.append("")
        lines.append(f"Config: {self.config_path}")
        lines.append(
            f"        {'present' if self.config_exists else 'will be created on first launch'}"
        )
        lines.append("")
        lines.append("OVERALL: " + ("OK" if self.ok else "FAIL"))
        return "\n".join(lines)


def _check(name: str) -> ImportCheck:
    """Probe importability of one module. Captures the exception message
    on failure so the user can see *why* (e.g. wrong arch, missing DLL)."""
    try:
        importlib.import_module(name)
        return ImportCheck(name=name, importable=True)
    except Exception as e:  # noqa: BLE001 — failures are the point
        # `str(e)` on ImportError tends to be informative ("No module
        # named X", "DLL load failed: …"). For other exception types we
        # use the type name as a hint.
        detail = str(e).strip().splitlines()[0] if str(e) else type(e).__name__
        return ImportCheck(name=name, importable=False, detail=detail)


def collect_diagnostic_report(
    *,
    on_windows: bool | None = None,
    config_path_factory: Any = None,
) -> DiagnosticReport:
    """Probe the environment and return a `DiagnosticReport`.

    `on_windows` and `config_path_factory` are injectable so tests can
    drive the off-Windows path even on a Windows host (and vice versa)
    without monkeypatching `sys.platform`.
    """
    if on_windows is None:
        on_windows = sys.platform == "win32"
    if config_path_factory is None:
        from .adapters.json_config import (
            default_config_path as config_path_factory,  # type: ignore[no-redef]
        )

    # core/ports/adapters/ui — anything we ship in the package — must
    # import. If any of these fails the build is broken.
    required = [
        _check("windows_rectangle.core.actions"),
        _check("windows_rectangle.core.dispatcher"),
        _check("windows_rectangle.app"),
        _check("windows_rectangle.adapters.json_config"),
    ]
    # PySide6 + pywin32 are technically optional (the headless path works
    # without them), but a user expecting the tray UX needs both.
    optional = [
        _check("PySide6"),
    ]
    if on_windows:
        # On Windows pywin32 is essentially required for the tray
        # experience, but the headless mode + the diagnostic itself
        # don't need it — keep in optional, not required.
        optional.append(_check("win32api"))

    cfg_path: Path = config_path_factory()
    return DiagnosticReport(
        version=__version__,
        python=sys.version.split()[0],
        platform=platform.platform(),
        required=required,
        optional=optional,
        config_path=str(cfg_path),
        config_exists=cfg_path.exists(),
    )


def run_check_install(*, json_output: bool = False) -> int:
    """Entry point for the `--check-install` CLI flag.

    Returns 0 iff every required check passed, 1 otherwise — caller is
    expected to propagate via `sys.exit`.
    """
    report = collect_diagnostic_report()
    if json_output:
        print(report.to_json())
    else:
        print(report.to_text())
    return 0 if report.ok else 1
