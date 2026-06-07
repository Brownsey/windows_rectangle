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

from ..core.actions import DEFAULT_SHORTCUTS, Action
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
        import contextlib

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _to_dict(settings)
        # Atomic write: temp file in the same directory, then rename.
        # Same-directory rename is atomic on Windows + POSIX.
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 -- delete=False is correct here
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
            with contextlib.suppress(OSError):
                os.unlink(tmp.name)
            raise


# ----- (de)serialisation ---------------------------------------------


def _to_dict(settings: Settings) -> dict:
    data = asdict(settings)
    # Serialise EVERY known Action — explicit empty string for actions
    # the user deliberately unbound (via clear_shortcut), missing-from-
    # dict for actions that just never got a default. This ensures a
    # cleared shortcut survives a save+load round-trip; otherwise the
    # loader would re-populate it from DEFAULT_SHORTCUTS on next start.
    data["shortcuts"] = {
        a.value: settings.shortcuts.get(a, "") for a in Action
    }
    data["schema_version"] = SCHEMA_VERSION
    return data


def _from_dict(raw: dict) -> Settings:
    """Tolerant decode.

    - Unknown shortcut keys: silently dropped (forward-compat with older
      versions that wrote actions we no longer recognise).
    - Empty-string combo: explicit "unbound" marker — the action is
      kept OUT of the resulting shortcuts dict (so rebind_hotkeys won't
      register anything for it).
    - Action missing entirely from the saved dict: fall back to the
      DEFAULT_SHORTCUTS binding (forward-compat with future Actions
      added after the user's last save).
    - Other missing fields: dataclass defaults.
    """
    defaults = Settings()
    shortcuts_raw = raw.get("shortcuts") or {}
    shortcuts: dict[Action, str] = {}
    for action in Action:
        if action.value in shortcuts_raw:
            combo = shortcuts_raw[action.value]
            if isinstance(combo, str) and combo:
                shortcuts[action] = combo
            # else: empty string or non-str → leave unbound.
        elif action in DEFAULT_SHORTCUTS:
            shortcuts[action] = DEFAULT_SHORTCUTS[action]

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
