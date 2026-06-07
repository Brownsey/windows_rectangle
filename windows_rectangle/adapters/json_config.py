"""JSON `ConfigStore` adapter — persists `Settings` to disk.

Pure stdlib (`json`, `pathlib`, `os`); no win32. Safe to unit-test on any
platform with `tmp_path`. The Windows-specific bit (resolving `%APPDATA%`)
is a single helper so tests can inject any path.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..core.actions import DEFAULT_SHORTCUTS, Action
from ..ports.config_store import Settings

SCHEMA_VERSION = 1

_log = logging.getLogger(__name__)


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
        except (OSError, json.JSONDecodeError) as e:
            # Corrupt or unreadable: fall back to defaults rather than
            # crash, but log a warning so the user sees *something*
            # (otherwise a partially-zapped config silently reverts to
            # defaults and the user is left wondering why their custom
            # shortcuts didn't load). Hand-edit bugs are the most common
            # cause; the log line gives the path to look at.
            _log.warning(
                "config at %s is unreadable, falling back to defaults: %s",
                self.path,
                e,
            )
            return Settings()
        return _from_dict(raw)

    def save(self, settings: Settings) -> None:
        self._atomic_write(self.path, _to_dict(settings))

    # ----- backup / migration helpers --------------------------------

    def export_to(self, destination: str | Path, settings: Settings | None = None) -> Path:
        """Write `settings` (or the currently-loaded settings) to `destination`.

        Used by `--export-config` for backup + cross-machine migration.
        Writes via the same atomic temp-file path as `save`, so a half-
        written export from a power cut can't corrupt the destination.
        Returns the resolved destination path.
        """
        dest = Path(destination).expanduser().resolve()
        if settings is None:
            settings = self.load()
        self._atomic_write(dest, _to_dict(settings))
        return dest

    def import_from(self, source: str | Path) -> Settings:
        """Read settings from `source` and persist them to `self.path`.

        Raises FileNotFoundError if the source is missing, JSONDecodeError
        if it's not valid JSON. Unknown fields / keys are tolerated by
        `_from_dict`'s lenient decode — a file produced by a newer
        version mostly works, and an older file picks up any new fields
        as their dataclass defaults.

        Used by `--import-config` for cross-machine migration; the caller
        can then `apply_settings(...)` to take effect without restart.
        """
        src = Path(source).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"import source does not exist: {src}")
        raw = json.loads(src.read_text(encoding="utf-8"))
        settings = _from_dict(raw)
        self.save(settings)
        return settings

    # ----- internals --------------------------------------------------

    @staticmethod
    def _atomic_write(target: Path, payload: dict) -> None:
        """Write JSON to `target` atomically via temp file + rename.

        Cleanup on error must close the handle BEFORE unlinking — on
        Windows `os.unlink` fails (PermissionError, an OSError) while
        any process holds an open handle to the file, and our
        `contextlib.suppress(OSError)` would then silently leak the
        .tmp into the target directory.
        """
        import contextlib

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 -- delete=False is correct here
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        )
        try:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, target)
        except Exception:
            with contextlib.suppress(Exception):
                tmp.close()  # idempotent; safe on already-closed file
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
