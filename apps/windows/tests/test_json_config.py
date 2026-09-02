"""Tests for windows_rectangle.adapters.json_config."""

import json

import pytest
from windows_rectangle.adapters.json_config import (
    SCHEMA_VERSION,
    JsonConfigStore,
    default_config_path,
)
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
)
from windows_rectangle.ports.config_store import Settings


@pytest.fixture
def store(tmp_path):
    return JsonConfigStore(tmp_path / "config.json")


def test_load_missing_file_returns_defaults(store):
    s = store.load()
    assert s == Settings()
    assert s.shortcuts == DEFAULT_SHORTCUTS


def test_save_then_load_roundtrips(store):
    original = Settings(gap=12, launch_at_login=True, cycle_idle_timeout=2.5)
    original.shortcuts[Action.MAXIMIZE] = "ctrl+shift+m"
    store.save(original)
    loaded = store.load()
    assert loaded.gap == 12
    assert loaded.launch_at_login is True
    assert loaded.cycle_idle_timeout == 2.5
    assert loaded.shortcuts[Action.MAXIMIZE] == "ctrl+shift+m"


def test_save_writes_schema_version(store):
    store.save(Settings())
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION


def test_workspace_round_trips_with_active_selection(store):
    workspace = Workspace(
        id="office",
        name="Office",
        shortcut="ctrl+alt+1",
        placements=(
            WorkspacePlacement(
                id="slack",
                name="Slack top left",
                matcher=WindowMatcher(process_name="slack.exe", title_contains="Slack"),
                rect=NormalizedRect(0, 0, 5000, 5000),
            ),
        ),
    )
    store.save(Settings(workspaces=(workspace,), active_workspace_id="office"))
    loaded = store.load()
    assert loaded.workspaces == (workspace,)
    assert loaded.active_workspace_id == "office"


def test_legacy_schema_loads_with_empty_workspaces(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"schema_version": 1, "gap": 7}), encoding="utf-8")
    loaded = store.load()
    assert loaded.gap == 7
    assert loaded.workspaces == ()
    assert loaded.active_workspace_id == ""


def test_malformed_workspaces_are_skipped_and_invalid_active_id_is_cleared(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "active_workspace_id": "broken",
                "workspaces": [
                    {"id": "broken", "name": "Broken", "placements": "not-a-list"},
                    {"id": "", "name": "Missing id", "placements": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.workspaces == ()
    assert loaded.active_workspace_id == ""


def test_save_creates_parent_dir(tmp_path):
    nested = tmp_path / "nested" / "dir" / "cfg.json"
    JsonConfigStore(nested).save(Settings())
    assert nested.exists()


def test_load_corrupt_json_falls_back_to_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not valid json", encoding="utf-8")
    assert store.load() == Settings()


def test_load_unknown_shortcut_key_ignored(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "shortcuts": {
                    "left_half": "ctrl+shift+left",
                    "obsolete_action": "ctrl+f12",  # not in Action enum
                },
                "gap": 7,
            }
        ),
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.gap == 7
    assert loaded.shortcuts[Action.LEFT_HALF] == "ctrl+shift+left"
    # Other actions still get their defaults.
    assert loaded.shortcuts[Action.RIGHT_HALF] == DEFAULT_SHORTCUTS[Action.RIGHT_HALF]


def test_load_missing_fields_use_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    # Only gap specified.
    store.path.write_text(json.dumps({"gap": 5}), encoding="utf-8")
    loaded = store.load()
    assert loaded.gap == 5
    assert loaded.launch_at_login is False  # default


def test_save_is_atomic_no_temp_left_on_success(store):
    store.save(Settings())
    siblings = list(store.path.parent.iterdir())
    # Exactly one file: the config. No `.tmp` remnant.
    assert siblings == [store.path]


def test_default_config_path_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = default_config_path()
    assert tmp_path in p.parents
    assert p.name == "config.json"


def test_default_config_path_falls_back_when_no_appdata(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    p = default_config_path()
    assert p.name == "config.json"
    assert ".windows_rectangle" in str(p)


def test_cleared_shortcut_survives_round_trip(store):
    """A user who clears a shortcut via prefs must not see it come back
    on the next launch — empty string is the persisted 'unbound' marker."""
    s = Settings()
    s.shortcuts.pop(Action.LEFT_HALF)  # simulate clear_shortcut
    store.save(s)
    loaded = store.load()
    assert Action.LEFT_HALF not in loaded.shortcuts


def test_unknown_shortcut_key_in_json_is_dropped(store):
    """Forward-compat: an action we don't recognise (e.g. from a newer
    version's file written by an older binary) must be silently ignored."""
    payload = {
        "shortcuts": {"left_half": "ctrl+alt+left", "phantom_action_xyz": "ctrl+f12"},
        "schema_version": SCHEMA_VERSION,
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload))
    loaded = store.load()
    assert loaded.shortcuts[Action.LEFT_HALF] == "ctrl+alt+left"


def test_all_shortcuts_cleared_round_trips_to_empty_dict(store):
    """A user who clears every shortcut (extreme case) gets back an empty
    shortcuts dict, not the defaults — same persistence contract as a
    single cleared shortcut."""
    s = Settings(shortcuts={})
    store.save(s)
    loaded = store.load()
    assert loaded.shortcuts == {}


def test_loading_legacy_payload_without_shortcuts_key_uses_defaults(store):
    """A pre-iter-57 config file may not have a shortcuts key at all
    (or have it explicitly null). Both cases should fall back to
    DEFAULT_SHORTCUTS, not crash and not silently produce an empty dict."""
    for payload in (
        {"schema_version": SCHEMA_VERSION},  # missing key
        {"shortcuts": None, "schema_version": SCHEMA_VERSION},  # explicit null
    ):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(json.dumps(payload))
        loaded = store.load()
        assert loaded.shortcuts == DEFAULT_SHORTCUTS


def test_future_action_falls_back_to_default(store):
    """Forward-compat the other direction: if the saved JSON predates a
    new Action being added (we simulate by omitting LEFT_HALF), that
    action falls back to its default binding rather than ending up unbound."""
    payload = {
        "shortcuts": {
            a.value: c for a, c in DEFAULT_SHORTCUTS.items() if a is not Action.LEFT_HALF
        },
        "schema_version": SCHEMA_VERSION,
    }
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(payload))
    loaded = store.load()
    assert loaded.shortcuts[Action.LEFT_HALF] == DEFAULT_SHORTCUTS[Action.LEFT_HALF]


# ----- export / import (cross-machine migration) ----------------------


def test_export_to_writes_json_file(store, tmp_path):
    """`export_to` snapshots the on-disk settings to a chosen destination
    — used for backups + moving config between machines."""
    s = Settings(gap=22)
    s.shortcuts[Action.MAXIMIZE] = "ctrl+shift+space"
    store.save(s)

    dest = tmp_path / "export" / "snapshot.json"
    out = store.export_to(dest)
    assert out == dest.resolve()
    assert dest.exists()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["gap"] == 22
    assert data["shortcuts"]["maximize"] == "ctrl+shift+space"


def test_export_to_accepts_explicit_settings(store, tmp_path):
    """Caller can pass settings directly (e.g. the prefs dialog's
    staged copy) so the export reflects what's about to be saved
    rather than re-loading from disk."""
    dest = tmp_path / "export.json"
    explicit = Settings(gap=99)
    store.export_to(dest, settings=explicit)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["gap"] == 99


def test_export_is_atomic(store, tmp_path, monkeypatch):
    """If the JSON dump raises, the destination must not be touched —
    otherwise a power-cut during export would corrupt a previously-good
    snapshot. We monkeypatch json.dump on the adapter module's lookup
    and confirm no .json or .tmp survives the failure."""
    import windows_rectangle.adapters.json_config as adapter

    dest = tmp_path / "export.json"
    real_dump = adapter.json.dump

    def boom(*args, **kwargs):
        real_dump(*args, **kwargs)  # write to the tmp file first
        raise RuntimeError("simulated failure mid-export")

    monkeypatch.setattr(adapter.json, "dump", boom)
    with pytest.raises(RuntimeError):
        store.export_to(dest)
    assert not dest.exists()
    # No leaked .tmp either.
    leftovers = list(dest.parent.glob("export.json.*.tmp"))
    assert leftovers == []


def test_import_from_loads_and_persists(store, tmp_path):
    """import_from reads JSON, parses through _from_dict's lenient
    decode, then atomically persists to self.path so the next launch
    picks up the imported settings."""
    src = tmp_path / "src.json"
    src.write_text(
        json.dumps(
            {
                "gap": 17,
                "launch_at_login": False,
                "drag_to_edge_enabled": True,
                "cycle_idle_timeout": 1.0,
                "almost_maximize_scale": 0.85,
                "shortcuts": {a.value: c for a, c in DEFAULT_SHORTCUTS.items()},
                "schema_version": SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )
    returned = store.import_from(src)
    assert returned.gap == 17
    # Now the store's on-disk file reflects the import.
    loaded = store.load()
    assert loaded.gap == 17


def test_import_from_missing_file_raises(store, tmp_path):
    with pytest.raises(FileNotFoundError):
        store.import_from(tmp_path / "nope.json")


def test_import_from_bad_json_raises(store, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        store.import_from(bad)


def test_load_corrupt_json_logs_warning(store, caplog):
    """A user with a syntactically-broken config gets defaults back, but
    also a log line with the path — otherwise the silent revert leaves
    them wondering why their bindings are gone."""
    import logging

    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not { json }", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="windows_rectangle.adapters.json_config"):
        settings = store.load()
    assert settings == Settings()
    # Path mentioned + the word "unreadable" make the line searchable in logs.
    assert any(str(store.path) in r.message and "unreadable" in r.message for r in caplog.records)


def test_export_then_import_round_trips(store, tmp_path):
    """Lock in the migration contract: export from A, import to B,
    settings come back equal field-for-field."""
    original = Settings(gap=8, drag_to_edge_enabled=False, almost_maximize_scale=0.5)
    original.shortcuts[Action.LEFT_HALF] = "ctrl+alt+shift+left"
    store.save(original)

    snapshot = tmp_path / "snap.json"
    store.export_to(snapshot)

    # Simulate a fresh machine with a different on-disk config.
    fresh = JsonConfigStore(tmp_path / "new_machine" / "config.json")
    fresh.import_from(snapshot)
    migrated = fresh.load()
    assert migrated.gap == 8
    assert migrated.drag_to_edge_enabled is False
    assert migrated.almost_maximize_scale == 0.5
    assert migrated.shortcuts[Action.LEFT_HALF] == "ctrl+alt+shift+left"
