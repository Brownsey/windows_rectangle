"""Tests for import-safe visual workspace canvas geometry."""

from windows_rectangle.core.workspaces import NormalizedRect
from windows_rectangle.ui.workspace_canvas import canvas_rect, resize_rect, translate_rect


def test_canvas_rect_maps_basis_points_inside_padding():
    assert canvas_rect(NormalizedRect(0, 0, 5000, 10000), 1036, 536, 18) == (
        18,
        18,
        500,
        500,
    )


def test_translate_rect_snaps_and_preserves_size():
    original = NormalizedRect(0, 0, 5000, 5000)
    moved = translate_rect(original, 250, 125, 1036, 536, padding=18)
    assert moved == NormalizedRect(2500, 2500, 7500, 7500)


def test_translate_rect_clamps_to_monitor_edges():
    original = NormalizedRect(5000, 5000, 10000, 10000)
    assert translate_rect(original, 9999, 9999, 800, 500) == original
    assert translate_rect(original, -9999, -9999, 800, 500) == NormalizedRect(0, 0, 5000, 5000)


def test_translate_rect_is_freeform_not_preset_snapped():
    original = NormalizedRect(0, 0, 5000, 5000)
    assert translate_rect(original, 13, 7, 1036, 536) == NormalizedRect(130, 140, 5130, 5140)


def test_resize_rect_supports_edges_and_corners():
    original = NormalizedRect(2000, 2000, 8000, 8000)
    assert resize_rect(
        original, frozenset({"right", "bottom"}), 100, 50, 1036, 536
    ) == NormalizedRect(2000, 2000, 9000, 9000)
    assert resize_rect(
        original, frozenset({"left", "top"}), -100, -50, 1036, 536
    ) == NormalizedRect(1000, 1000, 8000, 8000)


def test_resize_rect_enforces_minimum_and_monitor_bounds():
    original = NormalizedRect(2000, 2000, 8000, 8000)
    shrunk = resize_rect(original, frozenset({"left"}), 9999, 0, 1000, 500)
    bounded = resize_rect(original, frozenset({"right"}), 9999, 0, 1000, 500)
    assert shrunk.left == 7700
    assert bounded.right == 10000
