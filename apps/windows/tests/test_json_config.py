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


def test_save_then_load_preserves_blank_disabled_shortcut(store):
    original = Settings()
    original.shortcuts[Action.LEFT_HALF] = ""

    store.save(original)
    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == ""
    assert loaded.shortcuts[Action.RIGHT_HALF] == DEFAULT_SHORTCUTS[Action.RIGHT_HALF]


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


def test_load_non_object_json_falls_back_to_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[]", encoding="utf-8")
    assert store.load() == Settings()


def test_load_non_object_shortcuts_falls_back_to_default_shortcuts(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"shortcuts": ["bad"], "gap": 4}), encoding="utf-8")
    loaded = store.load()
    assert loaded.gap == 4
    assert loaded.shortcuts == DEFAULT_SHORTCUTS


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


def test_load_v1_legacy_default_shortcuts_migrates_to_current_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "shortcuts": {
                    "left_half": "ctrl+alt+left",
                    "maximize": "ctrl+alt+enter",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    assert loaded.shortcuts[Action.MAXIMIZE] == DEFAULT_SHORTCUTS[Action.MAXIMIZE]


def test_load_v2_blank_former_disabled_defaults_migrate_to_current_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "shortcuts": {
                    "left_half": "",
                    "top_half": "",
                    "maximize": "",
                    "next_display": "",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == ""
    assert loaded.shortcuts[Action.TOP_HALF] == DEFAULT_SHORTCUTS[Action.TOP_HALF]
    assert loaded.shortcuts[Action.MAXIMIZE] == DEFAULT_SHORTCUTS[Action.MAXIMIZE]
    assert loaded.shortcuts[Action.NEXT_DISPLAY] == DEFAULT_SHORTCUTS[Action.NEXT_DISPLAY]


def test_load_v3_blank_shortcut_keeps_command_disabled(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "shortcuts": {
                    "maximize": "",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.MAXIMIZE] == ""


def test_load_v3_reserved_default_shortcuts_migrate_to_safe_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "shortcuts": {
                    "left_half": "ctrl+win+left",
                    "right_half": "ctrl+win+right",
                    "almost_maximize": "ctrl+win+enter",
                    "first_third": "ctrl+shift+left",
                    "top_left_quarter": "ctrl+win+insert",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == DEFAULT_SHORTCUTS[Action.LEFT_HALF]
    assert loaded.shortcuts[Action.RIGHT_HALF] == DEFAULT_SHORTCUTS[Action.RIGHT_HALF]
    assert loaded.shortcuts[Action.ALMOST_MAXIMIZE] == DEFAULT_SHORTCUTS[Action.ALMOST_MAXIMIZE]
    assert loaded.shortcuts[Action.FIRST_THIRD] == DEFAULT_SHORTCUTS[Action.FIRST_THIRD]
    assert loaded.shortcuts[Action.TOP_LEFT_QUARTER] == DEFAULT_SHORTCUTS[Action.TOP_LEFT_QUARTER]


def test_load_v4_custom_win_shortcut_is_preserved(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "shortcuts": {
                    "left_half": "ctrl+win+left",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == "ctrl+win+left"


def test_load_v1_custom_shortcuts_are_not_migrated(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "shortcuts": {
                    "left_half": "ctrl+alt+h",
                    "maximize": "ctrl+alt+m",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == "ctrl+alt+h"
    assert loaded.shortcuts[Action.MAXIMIZE] == "ctrl+alt+m"


def test_load_blank_shortcut_keeps_command_disabled(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps({"shortcuts": {"left_half": ""}}),
        encoding="utf-8",
    )

    loaded = store.load()

    assert loaded.shortcuts[Action.LEFT_HALF] == ""


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
