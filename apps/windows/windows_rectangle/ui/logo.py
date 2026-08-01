"""Logo discovery for source and packaged Windows builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path

LOGO_FILENAMES: tuple[str, ...] = (
    "windows.ico",
    "logo.ico",
    "app.ico",
    "windows.png",
    "logo.png",
    "app.png",
    "windows.webp",
    "logo.webp",
    "app.webp",
)

TRAY_LOGO_FILENAMES: tuple[str, ...] = (
    "tray_logo.ico",
    "tray_logo.png",
    "tray_logo.webp",
)


def find_logo_file() -> Path | None:
    return _find_first_logo_file(LOGO_FILENAMES)


def find_tray_logo_file() -> Path | None:
    return _find_first_logo_file(TRAY_LOGO_FILENAMES)


def _find_first_logo_file(filenames: tuple[str, ...]) -> Path | None:
    for directory in _logo_directories():
        for filename in filenames:
            candidate = directory / filename
            if candidate.is_file():
                return candidate
    return None


def build_qicon(qt_gui):
    icon_path = find_logo_file()
    if icon_path is not None:
        icon = qt_gui.QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    return qt_gui.QIcon()


def build_tray_qicon(qt_gui):
    icon_path = find_tray_logo_file()
    if icon_path is not None:
        pixmap = qt_gui.QPixmap(str(icon_path))
        if not pixmap.isNull():
            icon = qt_gui.QIcon()
            for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
                icon.addPixmap(_square_icon_pixmap(qt_gui, pixmap, size))
            if not icon.isNull():
                return icon
    return build_blank_qicon(qt_gui)


def build_blank_qicon(qt_gui):
    pixmap = qt_gui.QPixmap(16, 16)
    pixmap.fill(qt_gui.QColor(0, 0, 0, 0))
    return qt_gui.QIcon(pixmap)


def _square_icon_pixmap(qt_gui, pixmap, size: int):
    source_side = min(pixmap.width(), pixmap.height())
    source_x = max(0, (pixmap.width() - source_side) // 2)
    source_y = max(0, (pixmap.height() - source_side) // 2)
    cropped = pixmap.copy(source_x, source_y, source_side, source_side)
    return cropped.scaled(
        size,
        size,
        qt_gui.Qt.AspectRatioMode.IgnoreAspectRatio,
        qt_gui.Qt.TransformationMode.SmoothTransformation,
    )


def build_logo_pixmap(qt_gui, *, max_width: int = 160, max_height: int = 44):
    logo_path = find_logo_file()
    if logo_path is None:
        return qt_gui.QPixmap()

    pixmap = qt_gui.QPixmap(str(logo_path))
    if pixmap.isNull():
        return qt_gui.QPixmap()

    return pixmap.scaled(
        max_width,
        max_height,
        qt_gui.Qt.AspectRatioMode.KeepAspectRatio,
        qt_gui.Qt.TransformationMode.SmoothTransformation,
    )


def _logo_directories() -> tuple[Path, ...]:
    directories: list[Path] = []
    env_dir = os.environ.get("WINDOWS_RECTANGLE_LOGO_DIR")
    if env_dir:
        directories.append(Path(env_dir))

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        directories.append(Path(meipass) / "logo")

    if getattr(sys, "frozen", False):
        directories.append(Path(sys.executable).resolve().parent / "logo")

    directories.append(_repo_root() / "logo")
    return tuple(dict.fromkeys(directories))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]
