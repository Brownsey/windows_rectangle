"""Tests for windows_rectangle.adapters.json_config."""

import json

import pytest

from windows_rectangle.adapters.json_config import (
    SCHEMA_VERSION,
    JsonConfigStore,
    default_config_path,
)
from windows_rectangle.core.actions import Action, DEFAULT_SHORTCUTS
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
