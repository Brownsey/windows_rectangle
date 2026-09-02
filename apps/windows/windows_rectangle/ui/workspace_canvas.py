"""Import-safe geometry and lazy Qt canvas for visual workspace editing."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..core.workspaces import BASIS, NormalizedRect, WorkspacePlacement

CANVAS_PADDING = 18
MIN_RECT_SIZE = 300


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
            self.setMinimumHeight(230)
            self.setMouseTracking(True)
            self._placements: tuple[WorkspacePlacement, ...] = ()
            self._selected = ""
            self._drag_origin = None
            self._original_rect = None
            self._resize_edges: frozenset[str] = frozenset()

        def set_placements(
            self, placements: Sequence[WorkspacePlacement], selected: str = ""
        ) -> None:
            self._placements = tuple(placements)
            self._selected = selected
            self.update()

        def select(self, placement_id: str) -> None:
            self._selected = placement_id
            self.update()

        def paintEvent(self, _event) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            monitor = self.rect().adjusted(
                CANVAS_PADDING, CANVAS_PADDING, -CANVAS_PADDING, -CANVAS_PADDING
            )
            painter.setPen(QtGui.QPen(QtGui.QColor("#98a2b3"), 1))
            painter.setBrush(QtGui.QColor("#eef2f6"))
            painter.drawRoundedRect(monitor, 9, 9)
            colors = ("#2e90fa", "#7f56d9", "#12b76a", "#f79009", "#e04f5f")
            for index, placement in enumerate(self._placements):
                x, y, width, height = canvas_rect(placement.rect, self.width(), self.height())
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
                painter.setPen(QtGui.QColor("white"))
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

        def mousePressEvent(self, event) -> None:
            if event.button() != QtCore.Qt.LeftButton:
                return
            point = event.position().toPoint()
            for placement in reversed(self._placements):
                x, y, width, height = canvas_rect(placement.rect, self.width(), self.height())
                if QtCore.QRect(x, y, width, height).contains(point):
                    self._selected = placement.id
                    self._drag_origin = point
                    self._original_rect = placement.rect
                    self._resize_edges = _edges_at(point, QtCore.QRect(x, y, width, height))
                    on_select(placement.id)
                    self.update()
                    return

        def mouseMoveEvent(self, event) -> None:
            if self._drag_origin is None or self._original_rect is None:
                return
            delta = event.position().toPoint() - self._drag_origin
            if self._resize_edges:
                preview = resize_rect(
                    self._original_rect,
                    self._resize_edges,
                    delta.x(),
                    delta.y(),
                    self.width(),
                    self.height(),
                )
            else:
                preview = translate_rect(
                    self._original_rect,
                    delta.x(),
                    delta.y(),
                    self.width(),
                    self.height(),
                )
            self._placements = tuple(
                placement
                if placement.id != self._selected
                else WorkspacePlacement(
                    placement.id,
                    placement.name,
                    placement.matcher,
                    preview,
                    placement.monitor_index,
                )
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
                on_move(placement.id, placement.rect)

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
