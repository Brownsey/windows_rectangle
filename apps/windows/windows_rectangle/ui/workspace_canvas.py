"""Import-safe geometry and lazy Qt canvas for visual workspace editing."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import replace

from ..core.workspaces import BASIS, NormalizedRect, WorkspacePlacement

CANVAS_PADDING = 18
MIN_RECT_SIZE = 300
DISPLAY_GAP = 12
DISPLAY_LABEL_HEIGHT = 22


def canvas_rect(
    rect: NormalizedRect, width: int, height: int, padding: int = CANVAS_PADDING
) -> tuple[int, int, int, int]:
    usable_width = max(1, width - padding * 2)
    usable_height = max(1, height - padding * 2)
    left = padding + round(rect.left * usable_width / BASIS)
    top = padding + round(rect.top * usable_height / BASIS)
    right = padding + round(rect.right * usable_width / BASIS)
    bottom = padding + round(rect.bottom * usable_height / BASIS)
    return left, top, right - left, bottom - top


def display_canvas_rect(
    monitor_index: int,
    display_count: int,
    width: int,
    height: int,
    *,
    padding: int = CANVAS_PADDING,
    gap: int = DISPLAY_GAP,
) -> tuple[int, int, int, int]:
    """Return one non-overlapping display cell in a compact monitor grid."""
    count = max(1, display_count)
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    column = monitor_index % columns
    row = monitor_index // columns
    usable_width = max(columns, width - padding * 2 - gap * (columns - 1))
    usable_height = max(rows, height - padding * 2 - gap * (rows - 1))
    cell_width = max(1, usable_width // columns)
    cell_height = max(1, usable_height // rows)
    return (
        padding + column * (cell_width + gap),
        padding + row * (cell_height + gap),
        cell_width,
        cell_height,
    )


def display_content_rect(display: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, width, height = display
    return x + 4, y + DISPLAY_LABEL_HEIGHT, max(1, width - 8), max(1, height - 26)


def placement_canvas_rect(
    rect: NormalizedRect,
    display: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    x, y, width, height = display_content_rect(display)
    left = x + round(rect.left * width / BASIS)
    top = y + round(rect.top * height / BASIS)
    right = x + round(rect.right * width / BASIS)
    bottom = y + round(rect.bottom * height / BASIS)
    return left, top, right - left, bottom - top


def translate_rect(
    rect: NormalizedRect,
    dx_pixels: int,
    dy_pixels: int,
    width: int,
    height: int,
    *,
    padding: int = CANVAS_PADDING,
    snap: int = 1,
) -> NormalizedRect:
    usable_width = max(1, width - padding * 2)
    usable_height = max(1, height - padding * 2)
    dx = round(dx_pixels * BASIS / usable_width / snap) * snap
    dy = round(dy_pixels * BASIS / usable_height / snap) * snap
    new_left = min(max(0, rect.left + dx), BASIS - (rect.right - rect.left))
    new_top = min(max(0, rect.top + dy), BASIS - (rect.bottom - rect.top))
    return NormalizedRect(
        new_left,
        new_top,
        new_left + rect.right - rect.left,
        new_top + rect.bottom - rect.top,
    )


def resize_rect(
    rect: NormalizedRect,
    edges: frozenset[str],
    dx_pixels: int,
    dy_pixels: int,
    width: int,
    height: int,
    *,
    padding: int = CANVAS_PADDING,
    minimum: int = MIN_RECT_SIZE,
) -> NormalizedRect:
    """Resize selected edges with basis-point precision and safe bounds."""
    usable_width = max(1, width - padding * 2)
    usable_height = max(1, height - padding * 2)
    dx = round(dx_pixels * BASIS / usable_width)
    dy = round(dy_pixels * BASIS / usable_height)
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    if "left" in edges:
        left = min(max(0, left + dx), right - minimum)
    if "right" in edges:
        right = max(min(BASIS, right + dx), left + minimum)
    if "top" in edges:
        top = min(max(0, top + dy), bottom - minimum)
    if "bottom" in edges:
        bottom = max(min(BASIS, bottom + dy), top + minimum)
    return NormalizedRect(left, top, right, bottom)


def create_layout_canvas(
    on_move: Callable[[str, NormalizedRect], None],
    on_select: Callable[[str], None],
):
    """Create the Qt widget lazily so importing this module never requires PySide6."""
    from PySide6 import QtCore, QtGui, QtWidgets

    class LayoutCanvas(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("workspaceCanvas")
            self.setAccessibleName("Visual workspace layout")
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.setToolTip(
                "Select an app, then use arrow keys to move it. Use Ctrl+arrow keys to resize it."
            )
            self.setMinimumHeight(230)
            self.setMouseTracking(True)
            self._placements: tuple[WorkspacePlacement, ...] = ()
            self._selected = ""
            self._drag_origin = None
            self._original_rect = None
            self._resize_edges: frozenset[str] = frozenset()
            self._display_count = 1

        def set_placements(
            self, placements: Sequence[WorkspacePlacement], selected: str = ""
        ) -> None:
            self._placements = tuple(placements)
            self._selected = selected
            if self._placements:
                self._display_count = max(
                    self._display_count,
                    max(placement.monitor_index for placement in self._placements) + 1,
                )
            self._sync_accessibility()
            self.update()

        def set_display_count(self, count: int) -> None:
            self._display_count = max(1, count)
            self._sync_accessibility()
            self.update()

        def select(self, placement_id: str) -> None:
            self._selected = placement_id
            self._sync_accessibility()
            self.update()

        def _display_box(self, monitor_index: int) -> tuple[int, int, int, int]:
            return display_canvas_rect(
                monitor_index,
                self._display_count,
                self.width(),
                self.height(),
            )

        def _placement_box(self, placement: WorkspacePlacement) -> tuple[int, int, int, int]:
            return placement_canvas_rect(
                placement.rect,
                self._display_box(placement.monitor_index),
            )

        def _sync_accessibility(self) -> None:
            placement = next(
                (item for item in self._placements if item.id == self._selected),
                None,
            )
            if placement is None:
                self.setAccessibleDescription(
                    "Select an app in the table or canvas to inspect and adjust its position."
                )
                return
            rect = placement.rect
            self.setAccessibleDescription(
                f"{placement.name}, Display {placement.monitor_index + 1}, "
                f"left {rect.left / 100:g}%, top {rect.top / 100:g}%, "
                f"width {(rect.right - rect.left) / 100:g}%, "
                f"height {(rect.bottom - rect.top) / 100:g}%. "
                "Arrow keys move; Ctrl+arrow keys resize."
            )

        def paintEvent(self, _event) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            for monitor_index in range(self._display_count):
                monitor = QtCore.QRect(*self._display_box(monitor_index))
                painter.setPen(QtGui.QPen(QtGui.QColor("#98a2b3"), 1))
                painter.setBrush(QtGui.QColor("#eef2f6"))
                painter.drawRoundedRect(monitor, 9, 9)
                painter.setPen(QtGui.QColor("#475467"))
                painter.drawText(
                    monitor.adjusted(8, 3, -8, 0),
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop,
                    f"Display {monitor_index + 1}",
                )
            colors = ("#2e90fa", "#7f56d9", "#12b76a", "#f79009", "#e04f5f")
            for index, placement in enumerate(self._placements):
                x, y, width, height = self._placement_box(placement)
                box = QtCore.QRect(x, y, width, height)
                color = QtGui.QColor(colors[index % len(colors)])
                color.setAlpha(205 if placement.id == self._selected else 155)
                painter.setBrush(color)
                painter.setPen(
                    QtGui.QPen(QtGui.QColor("#175cd3"), 3)
                    if placement.id == self._selected
                    else QtGui.QPen(QtGui.QColor("white"), 1)
                )
                painter.drawRoundedRect(box.adjusted(2, 2, -2, -2), 7, 7)
                painter.setPen(QtGui.QColor("#101828"))
                painter.drawText(
                    box.adjusted(9, 7, -7, -7),
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop,
                    placement.name,
                )
                if placement.id == self._selected:
                    painter.setBrush(QtGui.QColor("white"))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#175cd3"), 1))
                    corners = (
                        box.topLeft(),
                        box.topRight(),
                        box.bottomLeft(),
                        box.bottomRight(),
                    )
                    for corner in corners:
                        painter.drawRect(QtCore.QRect(corner.x() - 4, corner.y() - 4, 8, 8))
            if self.hasFocus():
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor("#175cd3"), 2))
                painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

        def mousePressEvent(self, event) -> None:
            if event.button() != QtCore.Qt.LeftButton:
                return
            point = event.position().toPoint()
            for placement in reversed(self._placements):
                x, y, width, height = self._placement_box(placement)
                if QtCore.QRect(x, y, width, height).contains(point):
                    self._selected = placement.id
                    self._drag_origin = point
                    self._original_rect = placement.rect
                    self._resize_edges = _edges_at(point, QtCore.QRect(x, y, width, height))
                    self.setFocus(QtCore.Qt.MouseFocusReason)
                    on_select(placement.id)
                    self._sync_accessibility()
                    self.update()
                    return

        def mouseMoveEvent(self, event) -> None:
            if self._drag_origin is None or self._original_rect is None:
                return
            delta = event.position().toPoint() - self._drag_origin
            selected = next(
                placement for placement in self._placements if placement.id == self._selected
            )
            _x, _y, display_width, display_height = display_content_rect(
                self._display_box(selected.monitor_index)
            )
            if self._resize_edges:
                preview = resize_rect(
                    self._original_rect,
                    self._resize_edges,
                    delta.x(),
                    delta.y(),
                    display_width,
                    display_height,
                    padding=0,
                )
            else:
                preview = translate_rect(
                    self._original_rect,
                    delta.x(),
                    delta.y(),
                    display_width,
                    display_height,
                    padding=0,
                )
            self._placements = tuple(
                placement if placement.id != self._selected else replace(placement, rect=preview)
                for placement in self._placements
            )
            self.update()

        def mouseReleaseEvent(self, event) -> None:
            if event.button() != QtCore.Qt.LeftButton or self._drag_origin is None:
                return
            placement = next((item for item in self._placements if item.id == self._selected), None)
            self._drag_origin = None
            self._original_rect = None
            self._resize_edges = frozenset()
            if placement is not None:
                self._sync_accessibility()
                on_move(placement.id, placement.rect)

        def keyPressEvent(self, event) -> None:
            placement = next(
                (item for item in self._placements if item.id == self._selected),
                None,
            )
            directions = {
                QtCore.Qt.Key_Left: (-100, 0),
                QtCore.Qt.Key_Right: (100, 0),
                QtCore.Qt.Key_Up: (0, -100),
                QtCore.Qt.Key_Down: (0, 100),
            }
            delta = directions.get(event.key())
            if placement is None or delta is None:
                super().keyPressEvent(event)
                return
            dx, dy = delta
            rect = placement.rect
            if event.modifiers() & QtCore.Qt.ControlModifier:
                right = min(BASIS, max(rect.left + MIN_RECT_SIZE, rect.right + dx))
                bottom = min(BASIS, max(rect.top + MIN_RECT_SIZE, rect.bottom + dy))
                updated = NormalizedRect(rect.left, rect.top, right, bottom)
            else:
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                left = min(max(0, rect.left + dx), BASIS - width)
                top = min(max(0, rect.top + dy), BASIS - height)
                updated = NormalizedRect(left, top, left + width, top + height)
            self._placements = tuple(
                replace(item, rect=updated) if item.id == placement.id else item
                for item in self._placements
            )
            self._sync_accessibility()
            self.update()
            on_move(placement.id, updated)
            event.accept()

    def _edges_at(point, box) -> frozenset[str]:
        margin = 10
        edges: set[str] = set()
        if abs(point.x() - box.left()) <= margin:
            edges.add("left")
        elif abs(point.x() - box.right()) <= margin:
            edges.add("right")
        if abs(point.y() - box.top()) <= margin:
            edges.add("top")
        elif abs(point.y() - box.bottom()) <= margin:
            edges.add("bottom")
        return frozenset(edges)

    return LayoutCanvas()
