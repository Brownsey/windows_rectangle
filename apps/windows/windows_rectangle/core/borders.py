"""Invisible-border math (brief §5 #2).

Windows 10/11 reports a window rect via `GetWindowRect` that includes
a ~7px drop-shadow margin on each side. `DwmGetWindowAttribute` with
`DWMWA_EXTENDED_FRAME_BOUNDS` returns the *visible* frame. The delta
between the two is what we need to apply when *placing* a window:
the user thinks "left-half == flush against screen left", and we have
to pad the SetWindowPos call by the invisible margin to get that.

These helpers are pure — adapter measures via DWM, calls these.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Rect


@dataclass(frozen=True, slots=True)
class BorderInsets:
    """Per-side pixel insets of the invisible drop-shadow margin."""

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def is_zero(self) -> bool:
        return self.left == 0 and self.top == 0 and self.right == 0 and self.bottom == 0


def measure(window_rect: Rect, extended_frame: Rect) -> BorderInsets:
    """Compute the invisible-border insets.

    `window_rect` is `GetWindowRect`; `extended_frame` is the DWM-reported
    visible frame. Negative values are clamped to 0 (defensive — can
    happen for windows that don't have a DWM frame, e.g. console).
    """
    left = max(0, extended_frame.left - window_rect.left)
    top = max(0, extended_frame.top - window_rect.top)
    right = max(0, window_rect.right - extended_frame.right)
    bottom = max(0, window_rect.bottom - extended_frame.bottom)
    return BorderInsets(left=left, top=top, right=right, bottom=bottom)


def to_outer_rect(visible_rect: Rect, insets: BorderInsets) -> Rect:
    """Given the rect we want the user to *see*, return the outer rect
    to pass to `SetWindowPos`.

    Outer = visible expanded by the insets on each side.
    """
    if insets.is_zero:
        return visible_rect
    return Rect.from_ltrb(
        visible_rect.left - insets.left,
        visible_rect.top - insets.top,
        visible_rect.right + insets.right,
        visible_rect.bottom + insets.bottom,
    )


def to_visible_rect(outer_rect: Rect, insets: BorderInsets) -> Rect:
    """Inverse of `to_outer_rect` — useful for `get_window_rect` callers
    so the rest of the code thinks in visible coordinates only.
    """
    if insets.is_zero:
        return outer_rect
    return Rect.from_ltrb(
        outer_rect.left + insets.left,
        outer_rect.top + insets.top,
        outer_rect.right - insets.right,
        outer_rect.bottom - insets.bottom,
    )
