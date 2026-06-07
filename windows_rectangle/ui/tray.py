"""System tray icon — `QSystemTrayIcon` (brief §2 #15).

Lazy-imports PySide6 inside `install(...)` so the module is import-clean
even on systems without Qt. Tests don't need a display to load this file.

Menu items:
    Launch at login       ← checkable, toggles ctx.settings.launch_at_login
    Preferences…          ← placeholder hook for the prefs window (deferred)
    Quit                  ← runs ctx.shutdown() + QApplication.quit()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..app import AppContext


_log = logging.getLogger(__name__)


@dataclass(slots=True)
class TrayController:
    """Thin facade around a `QSystemTrayIcon` driven by an `AppContext`.

    Construct via `install(ctx)`; the QSystemTrayIcon is stored on the
    instance so the GC doesn't reap it under Qt's parent-tracking model.
    """

    ctx: "AppContext"
    icon: object | None = None
    menu: object | None = None
    actions: dict[str, object] | None = None
    on_open_preferences: Callable[[], None] | None = None


def install(ctx: "AppContext", *, on_open_preferences: Callable[[], None] | None = None) -> TrayController:
    """Create + show the tray icon. Requires PySide6 + a running QApplication.

    Returns a `TrayController` holding strong refs to the Qt objects so
    they outlive this function's frame.
    """
    from PySide6 import QtGui, QtWidgets
    from PySide6.QtCore import Qt

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
    """A generated white square icon — replace with a packaged PNG when shipping."""
    pixmap = QtGui.QPixmap(16, 16)
    pixmap.fill(QtGui.QColor(240, 240, 240))
    return QtGui.QIcon(pixmap)


def _toggle_launch(ctx: "AppContext", checked: bool) -> None:
    ctx.settings.launch_at_login = bool(checked)
    ctx.sync_autostart()
    if ctx.config_store is not None:
        try:
            ctx.config_store.save(ctx.settings)
        except Exception:  # noqa: BLE001
            _log.exception("config save failed")


def _quit(ctx: "AppContext") -> None:
    try:
        ctx.shutdown()
    finally:
        from PySide6 import QtWidgets
        QtWidgets.QApplication.quit()


def _noop() -> None:
    _log.info("Preferences window not yet implemented")
