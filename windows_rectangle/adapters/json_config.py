"""JSON `ConfigStore` adapter — persists `Settings` to disk.

Pure stdlib (`json`, `pathlib`, `os`); no win32. Safe to unit-test on any
platform with `tmp_path`. The Windows-specific bit (resolving `%APPDATA%`)
is a single helper so tests can inject any path.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..core.actions import Action, DEFAULT_SHORTCUTS
from ..ports.config_store import Settings


SCHEMA_VERSION = 1


def default_config_path() -> Path:
    """Resolve `%APPDATA%/windows_rectangle/config.json`.

    Falls back to `~/.windows_rectangle/config.json` on non-Windows so
    tests + dev work without env hacks.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "windows_rectangle" / "config.json"
    return Path.home() / ".windows_rectangle" / "config.json"


class JsonConfigStore:
    """File-backed `ConfigStore`. Atomic on save (write+rename)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    # ----- ConfigStore protocol -----

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable — fall back to defaults rather than crash.
            # The composition root will log; we just return clean state.
            return Settings()
        return _from_dict(raw)

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _to_dict(settings)
        # Atomic write: temp file in the same directory, then rename.
        # Same-directory rename is atomic on Windows + POSIX.
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self.path.parent),
            prefix=self.path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        try:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, self.path)
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            raise


# ----- (de)serialisation ---------------------------------------------


def _to_dict(settings: Settings) -> dict:
    data = asdict(settings)
    # Action enum keys are not JSON-serialisable by default.
    data["shortcuts"] = {a.value: combo for a, combo in settings.shortcuts.items()}
    data["schema_version"] = SCHEMA_VERSION
    return data


def _from_dict(raw: dict) -> Settings:
    """Tolerant decode — unknown shortcut keys are dropped, missing fields default."""
    defaults = Settings()
    shortcuts_raw = raw.get("shortcuts") or {}
    shortcuts: dict[Action, str] = dict(DEFAULT_SHORTCUTS)
    for key, combo in shortcuts_raw.items():
        try:
            action = Action(key)
        except ValueError:
            continue
        if isinstance(combo, str) and combo:
            shortcuts[action] = combo

    return Settings(
        shortcuts=shortcuts,
        gap=int(raw.get("gap", defaults.gap)),
        launch_at_login=bool(raw.get("launch_at_login", defaults.launch_at_login)),
        cycle_idle_timeout=float(raw.get("cycle_idle_timeout", defaults.cycle_idle_timeout)),
        drag_to_edge_enabled=bool(raw.get("drag_to_edge_enabled", defaults.drag_to_edge_enabled)),
        almost_maximize_scale=float(raw.get("almost_maximize_scale", defaults.almost_maximize_scale)),
    )
