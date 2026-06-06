"""Port: launch-at-login control (brief §2 #16).

The Windows implementation writes/removes an entry under
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. The port keeps
that detail out of `core` and out of the tray UI.
"""

from __future__ import annotations

from typing import Protocol


# App-wide identifier used as the registry value name and the
# CreateMutexW name (brief §6 single-instance guard).
APP_ID = "WindowsRectangle"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class AutoStart(Protocol):
    def is_enabled(self) -> bool: ...
    def enable(self, command_line: str) -> None: ...
    def disable(self) -> None: ...
