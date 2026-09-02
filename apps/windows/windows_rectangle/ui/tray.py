"""System tray icon — `QSystemTrayIcon` (brief §2 #15).

Lazy-imports PySide6 inside `install(...)` so the module is import-clean
even on systems without Qt. Tests don't need a display to load this file.

Menu items:
    Launch at login          ← checkable, toggles ctx.settings.launch_at_login
    Pause shortcuts          ← checkable, unregisters/re-registers all hotkeys
    Preferences…             ← opens the rebind-shortcuts dialog
    Cheat sheet…             ← read-only popup listing every action + combo
    Binding status…          ← X of Y bound; details of any failed combos
    Reload config from disk  ← re-reads JSON config (handy for power users)
    Open config folder…      ← opens %APPDATA%\\windows_rectangle in Explorer
    Open log file…           ← opens windows_rectangle.log for bug reports
    About…                   ← version + project link
    Quit                     ← runs ctx.shutdown() + QApplication.quit()
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
    tray.setToolTip(_tooltip_for(ctx))

    menu = QtWidgets.QMenu()

    launch = QtGui.QAction("Launch at login", menu, checkable=True)
    launch.setChecked(bool(ctx.settings.launch_at_login))
    launch.toggled.connect(lambda checked: _toggle_launch(ctx, checked))
    menu.addAction(launch)

    pause = QtGui.QAction("Pause shortcuts", menu, checkable=True)
    pause.setChecked(bool(getattr(ctx, "paused", False)))
    pause.toggled.connect(lambda checked: _toggle_pause(ctx, checked))
    menu.addAction(pause)

    prefs = QtGui.QAction("Preferences…", menu)
    prefs.triggered.connect(lambda: (on_open_preferences or _noop)())
    menu.addAction(prefs)

    workspaces_menu = menu.addMenu("Layouts")
    _populate_workspace_menu(workspaces_menu, ctx, tray)

    cheat = QtGui.QAction("Cheat sheet…", menu)
    cheat.triggered.connect(lambda: _show_cheat_sheet(ctx))
    menu.addAction(cheat)

    binding_status = QtGui.QAction("Binding status…", menu)
    binding_status.triggered.connect(lambda: _show_binding_status(ctx))
    menu.addAction(binding_status)

    reload_action = QtGui.QAction("Reload config from disk", menu)
    reload_action.triggered.connect(lambda: _reload_config(ctx, tray))
    menu.addAction(reload_action)

    open_folder = QtGui.QAction("Open config folder…", menu)
    open_folder.triggered.connect(lambda: _open_config_folder(ctx, tray))
    menu.addAction(open_folder)

    open_log = QtGui.QAction("Open log file…", menu)
    open_log.triggered.connect(lambda: _open_log_file(ctx, tray))
    menu.addAction(open_log)

    about = QtGui.QAction("About…", menu)
    about.triggered.connect(_show_about)
    menu.addAction(about)

    menu.addSeparator()

    quit_action = QtGui.QAction("Quit", menu)
    quit_action.triggered.connect(lambda: _quit(ctx))
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: _handle_activation(reason, on_open_preferences or _noop))
    tray.show()

    tc.icon = tray
    tc.menu = menu
    tc.actions = {
        "launch_at_login": launch,
        "pause": pause,
        "preferences": prefs,
        "workspaces": workspaces_menu,
        "cheat_sheet": cheat,
        "binding_status": binding_status,
        "reload_config": reload_action,
        "open_config_folder": open_folder,
        "open_log_file": open_log,
        "about": about,
        "quit": quit_action,
    }

    # Keep the visible tray state in sync with prefs-driven changes —
    # otherwise the tooltip + checkbox lag the actual Settings until
    # the next app restart.
    def _on_settings(_settings) -> None:
        try:
            tray.setToolTip(_tooltip_for(ctx))
            launch.blockSignals(True)
            launch.setChecked(bool(ctx.settings.launch_at_login))
            launch.blockSignals(False)
            pause.blockSignals(True)
            pause.setChecked(bool(getattr(ctx, "paused", False)))
            pause.blockSignals(False)
            _populate_workspace_menu(workspaces_menu, ctx, tray)
        except Exception:  # noqa: BLE001 — tray refresh failure is non-fatal
            _log.debug("tray refresh failed", exc_info=True)

    ctx.subscribe_settings(_on_settings)

    # First-run welcome balloon — fires only if AppContext was marked
    # first_run by bind_win32 (no config file on disk). Keeps repeat
    # launches noiseless. Best-effort: missing tray-notification
    # support / muted notifications must not break startup. QtWidgets
    # is already imported above (we constructed QSystemTrayIcon from it).
    if getattr(ctx, "first_run", False):
        try:
            tray.showMessage(
                "Windows Rectangle is running",
                "Right-click the tray icon for Preferences, Cheat sheet, or Quit.",
                QtWidgets.QSystemTrayIcon.Information,
                6000,  # 6s — long enough to read, not annoying
            )
        except Exception:  # noqa: BLE001
            _log.debug("first-run balloon failed", exc_info=True)

    return tc


def _populate_workspace_menu(menu, ctx: AppContext, tray) -> None:
    """Rebuild workspace actions after settings change without stale callbacks."""
    from PySide6 import QtGui

    menu.clear()
    capture = QtGui.QAction("Capture current layout…", menu)
    capture.triggered.connect(lambda: _capture_workspace(ctx, tray))
    menu.addAction(capture)
    manage = QtGui.QAction("Manage layouts…", menu)
    manage.triggered.connect(lambda: _manage_workspaces(ctx, tray))
    menu.addAction(manage)
    menu.addSeparator()
    if not ctx.settings.workspaces:
        empty = QtGui.QAction("No saved layouts", menu)
        empty.setEnabled(False)
        menu.addAction(empty)
        return
    for workspace in ctx.settings.workspaces:
        label = workspace.name
        if workspace.shortcut:
            label += f"\t{workspace.shortcut}"
        action = QtGui.QAction(label, menu)
        action.setData(workspace.id)
        action.triggered.connect(
            lambda _checked=False, workspace_id=workspace.id: _apply_named_workspace(
                ctx, workspace_id, tray
            )
        )
        menu.addAction(action)


def _capture_workspace(ctx: AppContext, tray) -> None:
    from PySide6 import QtWidgets

    name, accepted = QtWidgets.QInputDialog.getText(
        None,
        "Capture Layout",
        "Layout name:",
    )
    if not accepted or not name.strip():
        return
    try:
        workspace = ctx.capture_named_workspace(name.strip())
    except Exception as exc:  # noqa: BLE001
        _log.exception("layout capture failed")
        tray.showMessage("Layout capture failed", str(exc))
        return
    tray.showMessage(
        "Layout saved",
        f"{workspace.name}: {len(workspace.placements)} windows captured.",
    )


def _manage_workspaces(ctx: AppContext, tray) -> None:
    try:
        from .workspaces_dialog import show

        show(ctx)
    except Exception as exc:  # noqa: BLE001
        _log.exception("layout editor failed")
        tray.showMessage("Could not open layout editor", str(exc))


def _apply_named_workspace(ctx: AppContext, workspace_id: str, tray) -> None:
    try:
        queued = ctx.queue_workspace(workspace_id)
    except Exception as exc:  # noqa: BLE001
        _log.exception("layout restore failed")
        tray.showMessage("Layout restore failed", str(exc))
        return
    if queued:
        tray.showMessage("Launching & arranging", "Starting configured apps and finding windows…")
    else:
        tray.showMessage("Layout already running", "Wait for the current arrangement to finish.")


def workspace_result_text(result) -> str:
    counts: dict[str, int] = {}
    for placement in result.placements:
        counts[placement.status] = counts.get(placement.status, 0) + 1
    labels = (
        ("moved", "moved"),
        ("not_found", "not found"),
        ("blocked", "blocked"),
        ("launch_failed", "failed to launch"),
    )
    summary = [f"{counts[key]} {label}" for key, label in labels if counts.get(key)]
    return " · ".join(summary) if summary else "No layout windows were configured."


def _build_icon(QtGui):
    """Tiny 4-pane window-tile glyph drawn programmatically.

    Hand-drawn so the build pipeline doesn't need a packaged .png/.ico —
    one less file to keep in sync with the spec. The four panes hint at
    the halves/quarters tiling that's the app's whole purpose.
    """
    from .logo import build_tray_qicon, find_tray_logo_file

    if find_tray_logo_file() is not None:
        return build_tray_qicon(QtGui)

    # Render at 64 then let Qt scale down per-DPI — sharper than rendering
    # straight to 16×16 on hi-DPI displays.
    pixmap = QtGui.QPixmap(64, 64)
    pixmap.fill(QtGui.QColor(0, 0, 0, 0))  # transparent background
    painter = QtGui.QPainter(pixmap)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        bg = QtGui.QColor(34, 102, 187)  # mid blue (Rectangle-style)
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


def _handle_activation(reason, on_open_preferences: Callable[[], None]) -> None:
    from PySide6 import QtWidgets

    if reason in (
        QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
        QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
    ):
        on_open_preferences()


def _toggle_pause(ctx: AppContext, checked: bool) -> None:
    """Tray "Pause shortcuts" handler. Errors are caught + logged — a
    failure to flip the OS-level registration must not crash the tray."""
    try:
        if checked:
            ctx.pause_hotkeys()
        else:
            ctx.resume_hotkeys()
    except Exception:  # noqa: BLE001
        _log.exception("pause/resume toggle failed")


def _toggle_launch(ctx: AppContext, checked: bool) -> None:
    ctx.settings.launch_at_login = bool(checked)
    ctx.sync_autostart()
    if ctx.config_store is not None:
        try:
            ctx.config_store.save(ctx.settings)
        except Exception:  # noqa: BLE001
            _log.exception("config save failed")


def _tooltip_for(ctx: AppContext) -> str:
    """Compose the hover-text shown over the tray icon.

    Shows gap (always), binding count when a binding has fired, and
    a paused indicator so a user can't be fooled into thinking
    "0/22 bound" means broken when it actually means paused.

    When paused: the live numerator is 0 (nothing registered with
    Windows) but the denominator stays at would_bind_count so the
    user can still see how many bindings would come back on resume.
    """
    gap = getattr(ctx.settings, "gap", 0)
    paused = bool(getattr(ctx, "paused", False))
    report = getattr(ctx, "last_binding_report", None)
    suffix = " • paused" if paused else ""
    if report is None or report.total == 0:
        return f"Windows Rectangle • {gap}px gap{suffix}"
    denom = getattr(report, "would_bind_count", report.bound_count) + report.failed_count
    return f"Windows Rectangle • {gap}px gap • {report.bound_count}/{denom} shortcuts bound{suffix}"


def _show_binding_status(ctx: AppContext) -> None:
    """Pop a small info box with the current binding-success summary.

    Splits bound and failed sections so a user with one busted combo
    can see exactly which action + combo failed (e.g. another app owns
    ctrl+alt+left) without trawling through logs.
    """
    try:
        from PySide6 import QtWidgets

        from .binding_status_view import binding_status_html

        report = getattr(ctx, "last_binding_report", None)
        body = binding_status_html(report)
        box = QtWidgets.QMessageBox()
        box.setWindowTitle("Windows Rectangle — Binding status")
        box.setTextFormat(_text_format_rich())
        box.setText(body)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.exec()
    except Exception:  # noqa: BLE001
        _log.exception("binding status popup failed")


def _reload_config(ctx: AppContext, tray) -> None:
    """Re-read JSON config and apply. Shows a tray balloon either way so
    the user gets visible feedback (otherwise the click is silent and
    looks broken when settings happen to be unchanged)."""
    from PySide6 import QtWidgets

    ok = False
    try:
        ok = ctx.reload_config()
    except Exception:  # noqa: BLE001
        _log.exception("reload_config raised")
    if ok:
        msg, kind = "Config reloaded from disk.", QtWidgets.QSystemTrayIcon.Information
    else:
        msg, kind = (
            "Could not reload — no config store or load failed (see log).",
            QtWidgets.QSystemTrayIcon.Warning,
        )
    try:
        tray.showMessage("Windows Rectangle", msg, kind, 3500)
    except Exception:  # noqa: BLE001
        _log.debug("reload toast failed", exc_info=True)


def _open_log_file(ctx: AppContext, tray) -> None:
    """Open the rotating log file in the user's default text app.

    If the file doesn't exist yet (no log line has been emitted), open
    the parent folder instead so the user can find it once activity
    starts. Toast on "log not configured" so the click never feels broken.
    """
    from pathlib import Path

    from PySide6 import QtCore, QtGui, QtWidgets

    path = ctx.log_file_path()
    if path is None:
        try:
            tray.showMessage(
                "Windows Rectangle",
                "Logging is not configured for this session.",
                QtWidgets.QSystemTrayIcon.Warning,
                3500,
            )
        except Exception:  # noqa: BLE001
            _log.debug("open-log toast failed", exc_info=True)
        return
    target = Path(path)
    try:
        if target.exists():
            url = QtCore.QUrl.fromLocalFile(str(target))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            url = QtCore.QUrl.fromLocalFile(str(target.parent))
        QtGui.QDesktopServices.openUrl(url)
    except Exception:  # noqa: BLE001
        _log.exception("open log file failed: %s", path)


def _open_config_folder(ctx: AppContext, tray) -> None:
    """Open `%APPDATA%\\windows_rectangle\\` in Explorer.

    Uses `QDesktopServices.openUrl` so we stay on the Qt side of the
    Win32 boundary — no need to spawn `explorer.exe` ourselves. The
    folder is created if missing so the open never lands on a phantom
    directory (config might not have been saved yet on a totally fresh
    install path).
    """
    from pathlib import Path

    from PySide6 import QtCore, QtGui, QtWidgets

    folder = ctx.config_folder()
    if folder is None:
        try:
            tray.showMessage(
                "Windows Rectangle",
                "No config store wired — nothing to open.",
                QtWidgets.QSystemTrayIcon.Warning,
                3500,
            )
        except Exception:  # noqa: BLE001
            _log.debug("open-folder toast failed", exc_info=True)
        return
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        url = QtCore.QUrl.fromLocalFile(folder)
        QtGui.QDesktopServices.openUrl(url)
    except Exception:  # noqa: BLE001
        _log.exception("open config folder failed: %s", folder)


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
