"""Pure formatter that turns a list of `MonitorInfo` into a
text / JSON dump for the `--print-monitors` CLI subcommand.

Importable on any platform; the Win32 query that supplies the
`MonitorInfo` list lives in `adapters/win32_windows.py` and is only
exercised on Windows. The formatter itself is portable so the CLI
flow + tests are platform-neutral.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from .ports.window_manager import MonitorInfo


def monitors_to_dicts(monitors: Sequence[MonitorInfo]) -> list[dict]:
    """Serialise each `MonitorInfo` to a JSON-friendly dict.

    Fields match the names in `MonitorInfo` so `--print-monitors-json`
    is a stable shape downstream tooling can rely on.
    """
    return [
        {
            "handle": repr(m.handle),
            "is_primary": bool(m.is_primary),
            "bounds": {
                "x": m.bounds.x,
                "y": m.bounds.y,
                "width": m.bounds.width,
                "height": m.bounds.height,
            },
            "work_area": {
                "x": m.work_area.x,
                "y": m.work_area.y,
                "width": m.work_area.width,
                "height": m.work_area.height,
            },
            "taskbar_height_inferred": (
                m.bounds.height - m.work_area.height
            ),
        }
        for m in monitors
    ]


def monitors_to_text(monitors: Sequence[MonitorInfo]) -> str:
    """Human-readable two-line-per-monitor dump.

    Includes the work-area / bounds delta so a user with their taskbar
    hidden or on a non-bottom edge can see why the math went where it
    did.
    """
    if not monitors:
        return "No monitors detected."
    lines: list[str] = []
    for i, m in enumerate(monitors, 1):
        primary = "  (primary)" if m.is_primary else ""
        lines.append(f"Monitor {i}: handle={m.handle!r}{primary}")
        lines.append(
            f"  bounds   : x={m.bounds.x}  y={m.bounds.y}  "
            f"w={m.bounds.width}  h={m.bounds.height}"
        )
        lines.append(
            f"  work_area: x={m.work_area.x}  y={m.work_area.y}  "
            f"w={m.work_area.width}  h={m.work_area.height}"
        )
        taskbar_height = m.bounds.height - m.work_area.height
        if taskbar_height > 0:
            lines.append(f"  taskbar  : ~{taskbar_height}px (inferred)")
        lines.append("")
    return "\n".join(lines).rstrip()


def monitors_to_json(monitors: Sequence[MonitorInfo], indent: int | None = 2) -> str:
    return json.dumps(monitors_to_dicts(monitors), indent=indent, sort_keys=True)
