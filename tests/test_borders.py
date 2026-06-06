"""Tests for windows_rectangle.core.borders."""

from windows_rectangle.core.borders import (
    BorderInsets,
    measure,
    to_outer_rect,
    to_visible_rect,
)
from windows_rectangle.core.geometry import Rect


WINDOW_RECT = Rect(93, 100, 814, 607)
EXTENDED = Rect(100, 100, 800, 600)


def test_measure_typical_win10_window():
    assert measure(WINDOW_RECT, EXTENDED) == BorderInsets(left=7, top=0, right=7, bottom=7)


def test_measure_clamps_negative():
    insets = measure(Rect(0, 0, 100, 100), Rect(-5, -5, 110, 110))
    assert insets.left == 0 and insets.top == 0


def test_measure_no_dwm_frame_is_zero():
    assert measure(WINDOW_RECT, WINDOW_RECT).is_zero


def test_to_outer_rect_expands():
    visible = Rect(100, 100, 800, 600)
    insets = BorderInsets(left=7, right=7, bottom=7)
    assert to_outer_rect(visible, insets) == Rect.from_ltrb(93, 100, 907, 707)


def test_to_outer_rect_zero_insets_is_no_op():
    visible = Rect(10, 20, 100, 50)
    assert to_outer_rect(visible, BorderInsets()) is visible


def test_to_visible_rect_shrinks():
    insets = BorderInsets(left=7, right=7, bottom=7)
    assert to_visible_rect(Rect.from_ltrb(93, 100, 907, 707), insets) == Rect(100, 100, 800, 600)


def test_roundtrip_visible_to_outer_to_visible():
    insets = BorderInsets(left=7, top=2, right=7, bottom=7)
    visible = Rect(100, 100, 800, 600)
    assert to_visible_rect(to_outer_rect(visible, insets), insets) == visible
