"""System tray icon — `QSystemTrayIcon` (brief §2 #15).

Lazy-imports PySide6 inside `install(...)` so the module is import-clean
even on systems without Qt. Tests don't need a display to load this file.

Menu items:
    Launch at login       ← checkable, toggles ctx.settings.launch_at_login
    Preferences…          ← opens the rebind-shortcuts dialog
    Cheat sheet…          ← read-only popup listing every action + combo
    About…                ← version + project link
    Quit                  ← runs ctx.shutdown() + QApplication.quit()
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .. import __version__

if TYPE_CHECKING:
    from ..app import AppContext


_log = logging.getLogger(__name__)


@dataclass(slots=True)
class TrayController:
    """Thin facade around a `QSystemTrayIcon` driven by an `AppContext`.

    Construct via `install(ctx)`; the QSystemTrayIcon is stored on the
    instance so the GC doesn't reap it under Qt's parent-tracking model.
    """

    ctx: AppContext
    icon: object | None = None
    menu: object | None = None
    actions: dict[str, object] | None = None
    on_open_preferences: Callable[[], None] | None = None


def install(
    ctx: AppContext,
    *,
    on_open_preferences: Callable[[], None] | None = None,
) -> TrayController:
    """Create + show the tray icon. Requires PySide6 + a running QApplication.

    Returns a `TrayController` holding strong refs to the Qt objects so
    they outlive this function's frame.
    """
    from PySide6 import QtGui, QtWidgets

    tc = TrayController(ctx=ctx, on_open_preferences=on_open_preferences)

    icon = _build_icon(QtGui)
    tray = QtWidgets.QSystemTrayIcon(icon)
    tray.setToolTip(f"Windows Rectangle {getattr(ctx.settings, 'gap', 0)}px gap")

    menu = QtWidgets.QMenu()

    launch = QtGui.QAction("Launch at login", menu, checkable=True)
    launch.setChecked(bool(ctx.settings.launch_at_login))
    launch.toggled.connect(lambda checked: _toggle_launch(ctx, checked))
    menu.addAction(launch)

    prefs = QtGui.QAction("Preferences…", menu)
    prefs.triggered.connect(lambda: (on_open_preferences or _noop)())
    menu.addAction(prefs)

    cheat = QtGui.QAction("Cheat sheet…", menu)
    cheat.triggered.connect(lambda: _show_cheat_sheet(ctx))
    menu.addAction(cheat)

    about = QtGui.QAction("About…", menu)
    about.triggered.connect(_show_about)
    menu.addAction(about)

    menu.addSeparator()

    quit_action = QtGui.QAction("Quit", menu)
    quit_action.triggered.connect(lambda: _quit(ctx))
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    tc.icon = tray
    tc.menu = menu
    tc.actions = {
        "launch_at_login": launch,
        "preferences": prefs,
        "cheat_sheet": cheat,
        "about": about,
        "quit": quit_action,
    }

    # Keep the visible tray state in sync with prefs-driven changes —
    # otherwise the tooltip + checkbox lag the actual Settings until
    # the next app restart.
    def _on_settings(settings) -> None:
        try:
            tray.setToolTip(f"Windows Rectangle {settings.gap}px gap")
            launch.blockSignals(True)
            launch.setChecked(bool(settings.launch_at_login))
            launch.blockSignals(False)
        except Exception:  # noqa: BLE001 — tray refresh failure is non-fatal
            _log.debug("tray refresh failed", exc_info=True)

    ctx.subscribe_settings(_on_settings)
    return tc


def _build_icon(QtGui):
    """Tiny 4-pane window-tile glyph drawn programmatically.

    Hand-drawn so the build pipeline doesn't need a packaged .png/.ico —
    one less file to keep in sync with the spec. The four panes hint at
    the halves/quarters tiling that's the app's whole purpose.
    """
    # Render at 64 then let Qt scale down per-DPI — sharper than rendering
    # straight to 16×16 on hi-DPI displays.
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtGui.QColor(0, 0, 0, 0))  # transparent background
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        bg = QtGui.QColor(34, 102, 187)        # mid blue (Rectangle-style)
        fg = QtGui.QColor(245, 245, 250)
        painter.setBrush(bg)
        painter.setPen(QtGui.QPen(fg, 4))
        painter.drawRoundedRect(4, 4, 56, 56, 8, 8)
        # Four panes: two-pixel inset cross, panes slightly inset from frame.
        painter.setPen(QtGui.QPen(fg, 4))
        painter.drawLine(32, 10, 32, 54)
        painter.drawLine(10, 32, 54, 32)
    finally:
        painter.end()
    return QtGui.QIcon(pixmap)


def _toggle_launch(ctx: AppContext, checked: bool) -> None:
    ctx.settings.launch_at_login = bool(checked)
    ctx.sync_autostart()
    if ctx.config_store is not None:
        try:
            ctx.config_store.save(ctx.settings)
        except Exception:  # noqa: BLE001
            _log.exception("config save failed")


def _show_cheat_sheet(ctx: AppContext) -> None:
    """Pop a non-modal info box listing every action and its current combo.

    The cheat sheet HTML comes from `ui.cheat_sheet.cheat_sheet_html`, so
    this function is just the QMessageBox wiring. Errors are caught so a
    Qt hiccup can't crash the tray.
    """
    try:
        from PySide6 import QtWidgets

        from .cheat_sheet import cheat_sheet_html

        body = cheat_sheet_html(ctx.settings.shortcuts)
        box = QtWidgets.QMessageBox()
        box.setWindowTitle("Windows Rectangle — Cheat sheet")
        box.setTextFormat(_text_format_rich())
        box.setText(body)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()
    except Exception:  # noqa: BLE001
        _log.exception("cheat sheet popup failed")


def _show_about() -> None:
    try:
        from PySide6 import QtWidgets

        body = (
            f"<h3>Windows Rectangle {_html_escape(__version__)}</h3>"
            "<p>A Rectangle-for-Windows window manager.</p>"
            "<p>Tile, snap, and cycle windows via fully rebindable shortcuts.<br>"
            "Right-click the tray icon → <b>Preferences…</b> to rebind.</p>"
            "<p>License: MIT.</p>"
        )
        box = QtWidgets.QMessageBox()
        box.setWindowTitle("About Windows Rectangle")
        box.setTextFormat(_text_format_rich())
        box.setText(body)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()
    except Exception:  # noqa: BLE001
        _log.exception("about popup failed")


def _text_format_rich():
    """Return Qt's RichText enum value, lazy-imported.

    Inlined helper keeps `_show_cheat_sheet` and `_show_about` short.
    """
    from PySide6 import QtCore

    return QtCore.Qt.RichText


def _html_escape(s: str) -> str:
    """Defensive escape for any string we splice into HTML — keeps the
    About popup safe if `__version__` ever contains a stray `<`."""
    import html

    return html.escape(s)


def _quit(ctx: AppContext) -> None:
    try:
        ctx.shutdown()
    finally:
        from PySide6 import QtWidgets
        QtWidgets.QApplication.quit()


def _noop() -> None:
    _log.info("Preferences window not yet implemented")
