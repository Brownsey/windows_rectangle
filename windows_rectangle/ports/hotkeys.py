"""Port: global hotkey registration."""

from __future__ import annotations

from typing import Callable, Protocol


HotkeyCallback = Callable[[], None]


class HotkeyRegistrationError(Exception):
    """Raised when `RegisterHotKey` returns failure (combo already taken)."""


class Hotkeys(Protocol):
    """Registers global hotkeys and pumps Win32 messages on a private thread.

    Adapters dispatch into the dispatcher via a thread-safe queue (brief §5.6).
    """

    def register(self, combo: str, callback: HotkeyCallback) -> int:
        """Register `combo` (e.g. "ctrl+alt+left"). Returns an opaque id.

        Raises `HotkeyRegistrationError` if the combo is unavailable so the
        prefs UI can surface a conflict.
        """

    def unregister(self, hotkey_id: int) -> None: ...

    def unregister_all(self) -> None:
        """Used on shutdown (brief §5.11)."""
