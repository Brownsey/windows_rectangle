"""Tests for windows_rectangle.core.keymap."""

import pytest
from windows_rectangle.core.actions import DEFAULT_SHORTCUTS
from windows_rectangle.core.keymap import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    UnsupportedKeyError,
    modifier_mask,
    translate,
    vkey_for,
)
from windows_rectangle.core.shortcuts import parse


@pytest.mark.parametrize(
    "key,expected",
    [
        ("left", 0x25),
        ("right", 0x27),
        ("up", 0x26),
        ("down", 0x28),
        ("enter", 0x0D),
        ("backspace", 0x08),
        ("escape", 0x1B),
        ("insert", 0x2D),
        ("delete", 0x2E),
        ("pageup", 0x21),
        ("pagedown", 0x22),
        ("=", 0xBB),
        ("-", 0xBD),
        (",", 0xBC),
        (".", 0xBE),
    ],
)
def test_vkey_for_named(key, expected):
    assert vkey_for(key) == expected


@pytest.mark.parametrize(
    "ch,expected",
    [
        ("a", 0x41),
        ("z", 0x5A),
        ("0", 0x30),
        ("9", 0x39),
    ],
)
def test_vkey_for_ascii(ch, expected):
    assert vkey_for(ch) == expected


def test_vkey_for_function_keys():
    assert vkey_for("f1") == 0x70
    assert vkey_for("f12") == 0x7B
    assert vkey_for("f24") == 0x87


def test_vkey_for_unsupported_raises():
    with pytest.raises(UnsupportedKeyError):
        vkey_for("printscreen")
    with pytest.raises(UnsupportedKeyError):
        vkey_for("longname")


def test_modifier_mask_ctrl_alt():
    mask = modifier_mask(("ctrl", "alt"), no_repeat=False)
    assert mask == MOD_CONTROL | MOD_ALT


def test_modifier_mask_includes_norepeat_by_default():
    mask = modifier_mask(("ctrl",))
    assert mask & MOD_NOREPEAT


def test_modifier_mask_all_four():
    mask = modifier_mask(("ctrl", "alt", "shift", "win"), no_repeat=False)
    assert mask == MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN


def test_modifier_mask_unknown_raises():
    with pytest.raises(UnsupportedKeyError):
        modifier_mask(("hyper",))


def test_modifier_mask_empty_with_norepeat():
    assert modifier_mask((), no_repeat=True) == MOD_NOREPEAT
    assert modifier_mask((), no_repeat=False) == 0


def test_translate_ctrl_alt_left():
    mask, vk = translate(parse("ctrl+alt+left"), no_repeat=False)
    assert mask == MOD_CONTROL | MOD_ALT
    assert vk == 0x25


def test_translate_no_repeat_flag():
    mask, _ = translate(parse("ctrl+alt+left"))
    assert mask & MOD_NOREPEAT


def test_every_enabled_default_shortcut_translates():
    for action, combo in DEFAULT_SHORTCUTS.items():
        if not combo:
            continue
        mask, vk = translate(parse(combo))
        assert isinstance(mask, int)
        assert 0 < vk <= 0xFF, f"vkey out of range for {action}: {vk:#x}"
