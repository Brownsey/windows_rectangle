"""Port: single-instance guard (brief §6).

A second launch must surface the existing tray icon and exit rather than
running a second copy that contests global hotkeys with itself.
"""

from __future__ import annotations

from typing import Protocol

from .autostart import APP_ID


# Per-user named mutex — `Local\` prefix scopes to the user session so
# multiple users can each run their own instance.
DEFAULT_MUTEX_NAME = f"Local\\{APP_ID}.SingleInstance"


class SingleInstance(Protocol):
    def acquire(self) -> bool:
        """True if we are the first instance; False if another already holds it."""

    def release(self) -> None:
        """Release the guard on shutdown. Idempotent."""
