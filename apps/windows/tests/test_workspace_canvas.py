"""Tests for import-safe visual workspace canvas geometry."""

from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowMatcher,
    WorkspacePlacement,
)
from windows_rectangle.ui.workspace_canvas import canvas_rect, resize_rect, translate_rect

from windows_rectangle.ui import workspace_canvas


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


def test_multi_display_canvas_keeps_equal_positions_separate():
    first_display = workspace_canvas.display_canvas_rect(0, 2, 1000, 500)
    second_display = workspace_canvas.display_canvas_rect(1, 2, 1000, 500)
    same_position = NormalizedRect(0, 0, 10000, 10000)

    first = workspace_canvas.placement_canvas_rect(same_position, first_display)
    second = workspace_canvas.placement_canvas_rect(same_position, second_display)

    assert first_display[0] + first_display[2] < second_display[0]
    assert first[0] + first[2] < second[0]


def test_canvas_keyboard_moves_selected_placement_and_exposes_geometry():
    from PySide6 import QtCore, QtTest, QtWidgets
    from windows_rectangle.ui.workspace_canvas import create_layout_canvas

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    moved = []
    canvas = create_layout_canvas(lambda _placement_id, rect: moved.append(rect), lambda _id: None)
    placement = WorkspacePlacement(
        "client",
        "RuneLite",
        WindowMatcher(process_name="RuneLite.exe"),
        NormalizedRect(0, 0, 5000, 5000),
    )
    canvas.resize(800, 400)
    canvas.set_placements((placement,))
    canvas.select(placement.id)
    canvas.show()
    canvas.setFocus()
    app.processEvents()

    QtTest.QTest.keyClick(canvas, QtCore.Qt.Key_Right)
    app.processEvents()

    assert canvas.focusPolicy() == QtCore.Qt.StrongFocus
    assert moved[-1] == NormalizedRect(100, 0, 5100, 5000)
    assert "RuneLite" in canvas.accessibleDescription()
    assert "Display 1" in canvas.accessibleDescription()
    canvas.deleteLater()
    app.processEvents()


def test_canvas_paints_visible_keyboard_focus_outline():
    from PySide6 import QtGui, QtWidgets
    from windows_rectangle.ui.workspace_canvas import create_layout_canvas

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(window)
    other = QtWidgets.QLineEdit()
    canvas = create_layout_canvas(lambda *_: None, lambda *_: None)
    canvas.resize(600, 300)
    layout.addWidget(other)
    layout.addWidget(canvas)
    window.resize(640, 380)
    window.show()
    other.setFocus()
    app.processEvents()
    unfocused = canvas.grab().toImage().pixelColor(canvas.width() // 2, 1)

    canvas.setFocus()
    app.processEvents()
    focused = canvas.grab().toImage().pixelColor(canvas.width() // 2, 1)

    assert focused == QtGui.QColor("#175cd3")
    assert focused != unfocused
    window.deleteLater()
    app.processEvents()
