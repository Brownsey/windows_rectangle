"""Port: persistent user configuration.

Adapter persists to JSON in `%APPDATA%` (brief §3). `core/` stays unaware
of where the bytes live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..core.actions import DEFAULT_SHORTCUTS, Action


@dataclass(slots=True)
class Settings:
    """User-visible config — small, JSON-serialisable."""

    shortcuts: dict[Action, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    gap: int = 0
    launch_at_login: bool = False
    cycle_idle_timeout: float = 1.5
    drag_to_edge_enabled: bool = True
    almost_maximize_scale: float = 0.85


class ConfigStore(Protocol):
    def load(self) -> Settings: ...
    def save(self, settings: Settings) -> None: ...
