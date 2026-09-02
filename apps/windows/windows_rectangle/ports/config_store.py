"""Port: persistent user configuration.

Adapter persists to JSON in `%APPDATA%` (brief §3). `core/` stays unaware
of where the bytes live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..core.actions import DEFAULT_SHORTCUTS, Action
from ..core.workspaces import Workspace


@dataclass(slots=True)
class Settings:
    """User-visible config — small, JSON-serialisable.

    Every field here must be wired through `AppContext.apply_settings`
    so the prefs dialog's slider/checkbox actually affects runtime
    behaviour. Adding a new field without wiring it is a latent bug
    (see iter 60 fixing this for almost_maximize_scale).
    """

    # Action → "ctrl+alt+left" style combos. An action *missing* from
    # this dict is intentionally unbound (see brief §2 #15 + iter 57's
    # round-trip fix).
    shortcuts: dict[Action, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    # Pixels of inset around screen edges + between tiled windows.
    gap: int = 0
    # HKCU\...\Run registry entry (Win) / Memory adapter (test).
    launch_at_login: bool = False
    # Seconds before a repeated-shortcut press resets to the first
    # member of its cycle group instead of advancing.
    cycle_idle_timeout: float = 1.5
    # Master switch for the WH_MOUSE_LL hook; False at startup → hook
    # not installed at all (brief §5 #7, iter 43).
    drag_to_edge_enabled: bool = True
    # Fraction of work-area side length used by Action.ALMOST_MAXIMIZE
    # (brief §2 #7). Wired through dispatcher.almost_maximize_scale in
    # iter 60.
    almost_maximize_scale: float = 0.85
    # Named multi-window arrangements. Tuple keeps snapshots safe to share
    # between the runtime, preferences dialog, and config adapter.
    workspaces: tuple[Workspace, ...] = ()
    active_workspace_id: str = ""


class ConfigStore(Protocol):
    def load(self) -> Settings: ...
    def save(self, settings: Settings) -> None: ...
