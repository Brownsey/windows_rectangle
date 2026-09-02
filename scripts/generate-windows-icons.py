"""Create square Windows icon assets from the canonical squirrel tray artwork."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

repo_root = Path(__file__).resolve().parents[1]
logo_dir = repo_root / "logo"
source = QImage(str(logo_dir / "tray_logo.png"))
if source.isNull():
    raise SystemExit("Could not load logo/tray_logo.png")

# The canonical artwork is portrait with the badge in its upper-middle.
# Crop tightly around that badge so it remains readable at 16–32 px.
side = round(source.width() * 0.80)
left = (source.width() - side) // 2
top = round(source.height() * 0.20)
square = source.copy(left, top, side, side)

png = square.scaled(512, 512, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
ico = square.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
if not png.save(str(logo_dir / "windows.png"), "PNG"):
    raise SystemExit("Could not write logo/windows.png")
if not ico.save(str(logo_dir / "windows.ico"), "ICO"):
    raise SystemExit("Could not write logo/windows.ico")

print("Generated logo/windows.png and logo/windows.ico")
