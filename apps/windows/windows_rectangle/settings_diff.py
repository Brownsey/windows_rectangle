"""Settings diff utility — used by `--import-config --dry-run` to show
the user what would change before they commit.

Pure: takes two `Settings` and returns a list of human-readable change
lines. No Qt, no file IO.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from .ports.config_store import Settings


def diff_settings(current: Settings, incoming: Settings) -> list[str]:
    """Return a list of "field: current -> incoming" lines for every
    field whose value differs. Empty list when they're identical.

    Shortcuts get expanded per-action so the user can see which
    individual combo would change rather than just "shortcuts: dict ->
    dict". Both bound→unbound and unbound→bound show.
    """
    lines: list[str] = []
    # Scalar dataclass fields: gap, launch_at_login, etc. — but NOT
    # shortcuts; that gets the per-action treatment below.
    for f in fields(Settings):
        if f.name == "shortcuts":
            continue
        cur = getattr(current, f.name)
        inc = getattr(incoming, f.name)
        if cur != inc:
            lines.append(_format_change(f.name, cur, inc))

    # Per-action shortcut diff. Iterate the union of both keysets so a
    # cleared shortcut (bound -> unbound) and a newly-bound one
    # (unbound -> bound) both surface.
    all_actions = set(current.shortcuts) | set(incoming.shortcuts)
    for action in sorted(all_actions, key=lambda a: a.value):
        cur = current.shortcuts.get(action, "")
        inc = incoming.shortcuts.get(action, "")
        if cur != inc:
            lines.append(
                _format_change(
                    f"shortcuts[{action.value}]",
                    cur or "(unbound)",
                    inc or "(unbound)",
                )
            )
    return lines


def _format_change(name: str, current: Any, incoming: Any) -> str:
    return f"  {name}: {current!r} -> {incoming!r}"
