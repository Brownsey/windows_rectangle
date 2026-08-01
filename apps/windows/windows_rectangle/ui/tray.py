"""System tray icon using QSystemTrayIcon.

PySide6 is imported lazily inside `install()` so tests and headless runs can
import this module without a Qt installation or display server.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .logo import build_qicon

if TYPE_CHECKING:
    from ..app import AppContext


_log = logging.getLogger(__name__)


@dataclass(slots=True)
class TrayController:
    """Strong-reference holder for the tray icon and its Qt menu objects."""

    ctx: AppContext
    icon: object | None = None
    menu: object | None = None
    actions: dict[str, object] | None = None
    on_open_preferences: Callable[[], None] | None = None


def install(
    ctx: AppContext, *, on_open_preferences: Callable[[], None] | None = None
) -> TrayController:
    """Create and show the tray icon. Requires PySide6 and QApplication."""
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

    prefs = QtGui.QAction("Preferences...", menu)
    prefs.triggered.connect(lambda: (on_open_preferences or (lambda: _open_preferences(ctx)))())
    menu.addAction(prefs)

    menu.addSeparator()

    quit_action = QtGui.QAction("Quit", menu)
    quit_action.triggered.connect(lambda: _quit(ctx))
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    tc.icon = tray
    tc.menu = menu
    tc.actions = {"launch_at_login": launch, "preferences": prefs, "quit": quit_action}
    return tc


def _build_icon(QtGui):
    """Generated placeholder icon; replace with a packaged icon before shipping."""
    custom_icon = build_qicon(QtGui)
    if not custom_icon.isNull():
        return custom_icon
    pixmap = QtGui.QPixmap(16, 16)
    pixmap.fill(QtGui.QColor(240, 240, 240))
    return QtGui.QIcon(pixmap)


def _toggle_launch(ctx: AppContext, checked: bool) -> None:
    ctx.settings.launch_at_login = bool(checked)
    ctx.sync_autostart()
    if ctx.config_store is not None:
        try:
            ctx.config_store.save(ctx.settings)
        except Exception:  # noqa: BLE001
            _log.exception("config save failed")


def _quit(ctx: AppContext) -> None:
    try:
        ctx.shutdown()
    finally:
        from PySide6 import QtWidgets

        QtWidgets.QApplication.quit()


def _open_preferences(ctx: AppContext) -> None:
    try:
        from .preferences import show

        show(ctx)
    except Exception:  # noqa: BLE001
        _log.exception("could not open preferences")
