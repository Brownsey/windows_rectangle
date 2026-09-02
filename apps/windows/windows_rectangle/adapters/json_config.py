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
from ..core.workspaces import NormalizedRect, WindowMatcher, Workspace, WorkspacePlacement
from ..ports.config_store import Settings

SCHEMA_VERSION = 3

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
        if not isinstance(raw, dict):
            _log.warning("config at %s is not a JSON object, falling back to defaults", self.path)
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

        Used by `--import-config` for cross-machine migration; the caller
        can then `apply_settings(...)` to take effect without restart.
        Equivalent to `parse_path(source)` + `save(...)`.
        """
        settings = self.parse_path(source)
        self.save(settings)
        return settings

    @staticmethod
    def parse_path(source: str | Path) -> Settings:
        """Parse `source` into a Settings without persisting.

        Public counterpart to the private `_from_dict` — used by
        `--import-config --dry-run` to preview without writing, and
        by `import_from` itself.

        Raises FileNotFoundError if the source is missing, JSONDecodeError
        if it's not valid JSON. Unknown fields / keys are tolerated by
        the lenient `_from_dict` decode — a file produced by a newer
        version mostly works, and an older file picks up any new fields
        as their dataclass defaults.
        """
        src = Path(source).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"import source does not exist: {src}")
        raw = json.loads(src.read_text(encoding="utf-8"))
        return _from_dict(raw)

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
    data["shortcuts"] = {a.value: settings.shortcuts.get(a, "") for a in Action}
    data["workspaces"] = [_workspace_to_dict(workspace) for workspace in settings.workspaces]
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

    workspaces = tuple(
        workspace
        for item in raw.get("workspaces", [])
        if isinstance(item, dict) and (workspace := _workspace_from_dict(item)) is not None
    )
    active_workspace_id = str(raw.get("active_workspace_id", ""))
    if active_workspace_id and all(w.id != active_workspace_id for w in workspaces):
        active_workspace_id = ""

    return Settings(
        shortcuts=shortcuts,
        gap=int(raw.get("gap", defaults.gap)),
        launch_at_login=bool(raw.get("launch_at_login", defaults.launch_at_login)),
        cycle_idle_timeout=float(raw.get("cycle_idle_timeout", defaults.cycle_idle_timeout)),
        drag_to_edge_enabled=bool(raw.get("drag_to_edge_enabled", defaults.drag_to_edge_enabled)),
        almost_maximize_scale=float(
            raw.get("almost_maximize_scale", defaults.almost_maximize_scale)
        ),
        workspaces=workspaces,
        active_workspace_id=active_workspace_id,
    )


def _workspace_to_dict(workspace: Workspace) -> dict[str, object]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "shortcut": workspace.shortcut,
        "placements": [
            {
                "id": placement.id,
                "name": placement.name,
                "monitor_index": placement.monitor_index,
                "launch_command": placement.launch_command,
                "matcher": asdict(placement.matcher),
                "rect": asdict(placement.rect),
            }
            for placement in workspace.placements
        ],
    }


def _workspace_from_dict(raw: dict[str, object]) -> Workspace | None:
    """Decode one workspace; malformed user entries are skipped safely."""
    try:
        placements_raw = raw.get("placements", [])
        if not isinstance(placements_raw, list):
            return None
        placements: list[WorkspacePlacement] = []
        for item in placements_raw:
            if not isinstance(item, dict):
                return None
            matcher_raw = item.get("matcher")
            rect_raw = item.get("rect")
            if not isinstance(matcher_raw, dict) or not isinstance(rect_raw, dict):
                return None
            placements.append(
                WorkspacePlacement(
                    id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    monitor_index=int(item.get("monitor_index", 0)),
                    launch_command=str(item.get("launch_command", "")),
                    matcher=WindowMatcher(
                        process_name=str(matcher_raw.get("process_name", "")),
                        title_contains=str(matcher_raw.get("title_contains", "")),
                        title_regex=str(matcher_raw.get("title_regex", "")),
                    ),
                    rect=NormalizedRect(
                        left=int(rect_raw.get("left", -1)),
                        top=int(rect_raw.get("top", -1)),
                        right=int(rect_raw.get("right", -1)),
                        bottom=int(rect_raw.get("bottom", -1)),
                    ),
                )
            )
        return Workspace(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            shortcut=str(raw.get("shortcut", "")),
            placements=tuple(placements),
        )
    except (TypeError, ValueError):
        return None
