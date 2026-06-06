"""Window eligibility — pure predicate over style flags (brief §5.10).

The adapter resolves an HWND to these flags via `GetWindowLong` and
`DwmGetWindowAttribute`; we decide whether to operate on it. Keeping the
rules pure makes them easy to test and audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Flag, auto


class Capability(Flag):
    """What the dispatcher is allowed to do with this window."""

    NONE = 0
    MOVE = auto()
    RESIZE = auto()
    MOVE_AND_RESIZE = MOVE | RESIZE


@dataclass(frozen=True, slots=True)
class WindowFlags:
    """A snapshot of a window's classification, adapter-supplied.

    Bit-for-bit matches the brief §5.10 filter list. All fields default to
    False so tests can construct partial pictures.
    """

    has_caption: bool = False        # WS_CAPTION
    has_thick_frame: bool = False    # WS_THICKFRAME (resizeable border)
    is_tool_window: bool = False     # WS_EX_TOOLWINDOW
    is_shell_window: bool = False    # GetShellWindow / desktop
    is_cloaked: bool = False         # DWMWA_CLOAKED (UWP background apps)
    is_minimized: bool = False
    is_disabled: bool = False        # WS_DISABLED


def classify(flags: WindowFlags) -> Capability:
    """Decide what we can do with the window described by `flags`.

    Rules:
    - Reject shell, cloaked, disabled, tool, and minimized windows outright.
    - Require WS_CAPTION (so we don't try to move desktop panels/popups).
    - If WS_THICKFRAME absent → move-only (no resize). Per brief §5.10.
    """
    if flags.is_shell_window or flags.is_cloaked or flags.is_disabled:
        return Capability.NONE
    if flags.is_tool_window or flags.is_minimized:
        return Capability.NONE
    if not flags.has_caption:
        return Capability.NONE
    if not flags.has_thick_frame:
        return Capability.MOVE
    return Capability.MOVE_AND_RESIZE


def is_eligible(flags: WindowFlags) -> bool:
    """Convenience: anything we can act on at all."""
    return classify(flags) is not Capability.NONE
