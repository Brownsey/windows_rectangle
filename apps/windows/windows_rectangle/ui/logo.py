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


def find_logo_file() -> Path | None:
    for directory in _logo_directories():
        for filename in LOGO_FILENAMES:
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
