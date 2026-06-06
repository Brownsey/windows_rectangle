"""Launch-at-login via the Windows registry Run key.

Production adapter (`WinregAutoStart`) imports `winreg` lazily so the
module is importable on non-Windows for tests + CI. A `MemoryAutoStart`
in-memory implementation is provided for both unit tests and the
non-Windows dev path.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field

from ..ports.autostart import APP_ID, RUN_KEY_PATH


_log = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryAutoStart:
    """In-memory `AutoStart` for tests + non-Windows dev. Holds the value in RAM."""

    enabled: bool = False
    command_line: str | None = field(default=None)

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self, command_line: str) -> None:
        if not command_line:
            raise ValueError("command_line must be non-empty")
        self.enabled = True
        self.command_line = command_line

    def disable(self) -> None:
        self.enabled = False
        self.command_line = None


class WinregAutoStart:
    """Real Windows implementation. Writes HKCU\\...\\Run\\<APP_ID>.

    Raises OSError on registry failure (caller decides whether to surface).
    """

    def __init__(self, *, app_id: str = APP_ID, key_path: str = RUN_KEY_PATH) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WinregAutoStart requires Windows")
        self.app_id = app_id
        self.key_path = key_path

    # ----- AutoStart protocol -----

    def is_enabled(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path) as key:
                value, _type = winreg.QueryValueEx(key, self.app_id)
            return bool(value)
        except FileNotFoundError:
            return False
        except OSError:
            _log.exception("winreg query failed")
            return False

    def enable(self, command_line: str) -> None:
        if not command_line:
            raise ValueError("command_line must be non-empty")
        import winreg
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, self.app_id, 0, winreg.REG_SZ, command_line)

    def disable(self) -> None:
        import winreg
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self.app_id)
        except FileNotFoundError:
            return  # Already absent — desired state.


def best_available() -> "WinregAutoStart | MemoryAutoStart":
    """Pick `WinregAutoStart` on Windows, `MemoryAutoStart` everywhere else."""
    if sys.platform == "win32":
        return WinregAutoStart()
    return MemoryAutoStart()
