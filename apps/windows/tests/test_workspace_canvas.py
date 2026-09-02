"""Tests for import-safe visual workspace canvas geometry."""

from windows_rectangle.core.workspaces import NormalizedRect
from windows_rectangle.ui.workspace_canvas import canvas_rect, translate_rect


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
