"""JSON `ConfigStore` adapter — persists `Settings` to disk.

Pure stdlib (`json`, `pathlib`, `os`); no win32. Safe to unit-test on any
platform with `tmp_path`. The Windows-specific bit (resolving `%APPDATA%`)
is a single helper so tests can inject any path.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..core.actions import DEFAULT_SHORTCUTS, Action
from ..core.shortcuts import ShortcutParseError, normalise
from ..ports.config_store import Settings

SCHEMA_VERSION = 7

_FORMERLY_DISABLED_DEFAULT_ACTIONS: frozenset[Action] = frozenset(
    {
        Action.TOP_HALF,
        Action.BOTTOM_HALF,
        Action.CENTER_THIRD,
        Action.FIRST_TWO_THIRDS,
        Action.LAST_TWO_THIRDS,
        Action.MAXIMIZE,
        Action.MAXIMIZE_HEIGHT,
        Action.CENTER,
        Action.LARGER,
        Action.SMALLER,
        Action.RESTORE,
        Action.NEXT_DISPLAY,
        Action.PREV_DISPLAY,
    }
)

_LEGACY_DEFAULT_SHORTCUTS_V1: dict[Action, str] = {
    Action.LEFT_HALF: "ctrl+alt+left",
    Action.RIGHT_HALF: "ctrl+alt+right",
    Action.TOP_HALF: "ctrl+alt+up",
    Action.BOTTOM_HALF: "ctrl+alt+down",
    Action.TOP_LEFT_QUARTER: "ctrl+alt+u",
    Action.TOP_RIGHT_QUARTER: "ctrl+alt+i",
    Action.BOTTOM_LEFT_QUARTER: "ctrl+alt+j",
    Action.BOTTOM_RIGHT_QUARTER: "ctrl+alt+k",
    Action.FIRST_THIRD: "ctrl+alt+d",
    Action.CENTER_THIRD: "ctrl+alt+f",
    Action.LAST_THIRD: "ctrl+alt+g",
    Action.FIRST_TWO_THIRDS: "ctrl+alt+e",
    Action.LAST_TWO_THIRDS: "ctrl+alt+t",
    Action.MAXIMIZE: "ctrl+alt+enter",
    Action.MAXIMIZE_HEIGHT: "ctrl+alt+shift+up",
    Action.MAXIMIZE_WIDTH: "ctrl+alt+shift+right",
    Action.ALMOST_MAXIMIZE: "ctrl+alt+shift+enter",
    Action.CENTER: "ctrl+alt+c",
    Action.LARGER: "ctrl+alt+=",
    Action.SMALLER: "ctrl+alt+-",
    Action.RESTORE: "ctrl+alt+backspace",
    Action.NEXT_DISPLAY: "ctrl+alt+.",
    Action.PREV_DISPLAY: "ctrl+alt+,",
    Action.TOGGLE_ALWAYS_ON_TOP: "ctrl+alt+shift+space",
}

_RESERVED_DEFAULT_SHORTCUTS_V3: dict[Action, str] = {
    Action.LEFT_HALF: "ctrl+win+left",
    Action.RIGHT_HALF: "ctrl+win+right",
    Action.TOP_HALF: "ctrl+win+up",
    Action.BOTTOM_HALF: "ctrl+win+down",
    Action.TOP_LEFT_QUARTER: "ctrl+win+insert",
    Action.TOP_RIGHT_QUARTER: "ctrl+win+pageup",
    Action.BOTTOM_LEFT_QUARTER: "ctrl+win+delete",
    Action.BOTTOM_RIGHT_QUARTER: "ctrl+win+pagedown",
    Action.TOP_LEFT_SIXTH: "ctrl+shift+insert",
    Action.TOP_RIGHT_SIXTH: "ctrl+shift+pageup",
    Action.BOTTOM_LEFT_SIXTH: "ctrl+shift+delete",
    Action.BOTTOM_RIGHT_SIXTH: "ctrl+shift+pagedown",
    Action.FIRST_THIRD: "ctrl+shift+left",
    Action.CENTER_THIRD: "ctrl+shift+enter",
    Action.LAST_THIRD: "ctrl+shift+right",
    Action.FIRST_TWO_THIRDS: "ctrl+shift+home",
    Action.LAST_TWO_THIRDS: "ctrl+shift+end",
    Action.MAXIMIZE: "ctrl+alt+enter",
    Action.MAXIMIZE_HEIGHT: "ctrl+alt+shift+up",
    Action.MAXIMIZE_WIDTH: "ctrl+alt+shift+right",
    Action.ALMOST_MAXIMIZE: "ctrl+win+enter",
    Action.CENTER: "ctrl+alt+c",
    Action.LARGER: "ctrl+alt+=",
    Action.SMALLER: "ctrl+alt+-",
    Action.RESTORE: "ctrl+alt+backspace",
    Action.NEXT_DISPLAY: "ctrl+alt+.",
    Action.PREV_DISPLAY: "ctrl+alt+,",
    Action.TOGGLE_ALWAYS_ON_TOP: "ctrl+alt+shift+space",
}

_PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V4: dict[Action, str] = {
    Action.TOP_LEFT_SIXTH: "ctrl+alt+shift+u",
    Action.TOP_RIGHT_SIXTH: "ctrl+alt+shift+i",
    Action.BOTTOM_LEFT_SIXTH: "ctrl+alt+shift+j",
    Action.BOTTOM_RIGHT_SIXTH: "ctrl+alt+shift+k",
}

_PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V5: dict[Action, str] = {
    Action.TOP_LEFT_SIXTH: "ctrl+alt+shift+insert",
    Action.TOP_RIGHT_SIXTH: "ctrl+alt+shift+pageup",
    Action.BOTTOM_LEFT_SIXTH: "ctrl+alt+shift+delete",
    Action.BOTTOM_RIGHT_SIXTH: "ctrl+alt+shift+pagedown",
}

_PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V6: dict[Action, str] = {
    Action.TOP_LEFT_SIXTH: "ctrl+alt+insert",
    Action.TOP_RIGHT_SIXTH: "ctrl+alt+pageup",
    Action.BOTTOM_LEFT_SIXTH: "ctrl+alt+shift+delete",
    Action.BOTTOM_RIGHT_SIXTH: "ctrl+alt+pagedown",
}


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

    def __init__(self, path: str | Path | None = None) -> None:
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
        if not isinstance(raw, dict):
            return Settings()
        return _from_dict(raw)

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _to_dict(settings)
        # Atomic write: temp file in the same directory, then rename.
        # Same-directory rename is atomic on Windows + POSIX.
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp_name = tmp.name
                json.dump(payload, tmp, indent=2, sort_keys=True)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            if tmp_name is not None:
                with suppress(OSError):
                    os.unlink(tmp_name)
            raise


# ----- (de)serialisation ---------------------------------------------


def _to_dict(settings: Settings) -> dict[str, Any]:
    data = asdict(settings)
    # Action enum keys are not JSON-serialisable by default.
    data["shortcuts"] = {a.value: combo for a, combo in settings.shortcuts.items()}
    data["schema_version"] = SCHEMA_VERSION
    return data


def _from_dict(raw: dict[str, Any]) -> Settings:
    """Tolerant decode — unknown shortcut keys are dropped, missing fields default."""
    defaults = Settings()
    schema_version = _schema_version(raw.get("schema_version"))
    shortcuts_raw = raw.get("shortcuts")
    if not isinstance(shortcuts_raw, dict):
        shortcuts_raw = {}
    shortcuts: dict[Action, str] = dict(DEFAULT_SHORTCUTS)
    for key, combo in shortcuts_raw.items():
        if not isinstance(key, str):
            continue
        try:
            action = Action(key)
        except ValueError:
            continue
        if isinstance(combo, str):
            if schema_version < 2 and _matches_legacy_default(action, combo):
                continue
            if schema_version < 3 and _matches_former_disabled_default(action, combo):
                continue
            if schema_version < 4 and _matches_reserved_default(action, combo):
                continue
            if schema_version < 5 and _matches_previous_sixth_default(action, combo):
                continue
            if schema_version < 6 and _matches_previous_insert_sixth_default(action, combo):
                continue
            if schema_version < 7 and _matches_previous_ctrl_alt_insert_sixth_default(
                action, combo
            ):
                continue
            shortcuts[action] = combo

    return Settings(
        shortcuts=shortcuts,
        gap=int(raw.get("gap", defaults.gap)),
        launch_at_login=bool(raw.get("launch_at_login", defaults.launch_at_login)),
        cycle_idle_timeout=float(raw.get("cycle_idle_timeout", defaults.cycle_idle_timeout)),
        drag_to_edge_enabled=bool(raw.get("drag_to_edge_enabled", defaults.drag_to_edge_enabled)),
        almost_maximize_scale=float(
            raw.get("almost_maximize_scale", defaults.almost_maximize_scale)
        ),
    )


def _schema_version(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _matches_legacy_default(action: Action, combo: str) -> bool:
    legacy = _LEGACY_DEFAULT_SHORTCUTS_V1.get(action)
    if not legacy:
        return False
    try:
        return normalise(combo) == normalise(legacy)
    except ShortcutParseError:
        return combo.strip().lower() == legacy


def _matches_former_disabled_default(action: Action, combo: str) -> bool:
    return action in _FORMERLY_DISABLED_DEFAULT_ACTIONS and combo.strip() == ""


def _matches_reserved_default(action: Action, combo: str) -> bool:
    reserved_default = _RESERVED_DEFAULT_SHORTCUTS_V3.get(action)
    if not reserved_default:
        return False
    try:
        return normalise(combo) == normalise(reserved_default)
    except ShortcutParseError:
        return combo.strip().lower() == reserved_default


def _matches_previous_sixth_default(action: Action, combo: str) -> bool:
    previous_default = _PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V4.get(action)
    if not previous_default:
        return False
    try:
        return normalise(combo) == normalise(previous_default)
    except ShortcutParseError:
        return combo.strip().lower() == previous_default


def _matches_previous_insert_sixth_default(action: Action, combo: str) -> bool:
    previous_default = _PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V5.get(action)
    if not previous_default:
        return False
    try:
        return normalise(combo) == normalise(previous_default)
    except ShortcutParseError:
        return combo.strip().lower() == previous_default


def _matches_previous_ctrl_alt_insert_sixth_default(action: Action, combo: str) -> bool:
    previous_default = _PREVIOUS_SIXTH_DEFAULT_SHORTCUTS_V6.get(action)
    if not previous_default:
        return False
    try:
        return normalise(combo) == normalise(previous_default)
    except ShortcutParseError:
        return combo.strip().lower() == previous_default
