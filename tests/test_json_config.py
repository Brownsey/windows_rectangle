"""Tests for windows_rectangle.adapters.json_config."""

import json

import pytest

from windows_rectangle.adapters.json_config import (
    SCHEMA_VERSION,
    JsonConfigStore,
    default_config_path,
)
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS, Action
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
    store.path.write_text(json.dumps({
        "shortcuts": {
            "left_half": "ctrl+shift+left",
            "obsolete_action": "ctrl+f12",  # not in Action enum
        },
        "gap": 7,
    }), encoding="utf-8")
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
