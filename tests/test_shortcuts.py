"""Tests for windows_rectangle.core.shortcuts."""

import pytest

from windows_rectangle.core.shortcuts import (
    Combo,
    ShortcutParseError,
    conflicts,
    is_reserved,
    normalise,
    parse,
)


# ----- parse() --------------------------------------------------------

def test_parse_simple():
    assert parse("ctrl+alt+left") == Combo(("ctrl", "alt"), "left")


def test_parse_case_insensitive():
    assert parse("CTRL+Alt+LEFT") == Combo(("ctrl", "alt"), "left")


def test_parse_minus_key_is_preserved():
    # `-` is the SMALLER action's key (Ctrl+Alt+-) and must not be confused with a separator.
    assert parse("ctrl+alt+-") == Combo(("ctrl", "alt"), "-")


def test_parse_extra_spaces():
    assert parse(" ctrl + alt + left ") == Combo(("ctrl", "alt"), "left")


def test_parse_canonical_modifier_order():
    # Whatever order the user types, output is ctrl, alt, shift, win.
    c = parse("win+shift+alt+ctrl+a")
    assert c.modifiers == ("ctrl", "alt", "shift", "win")
    assert c.key == "a"


def test_parse_alias_modifiers():
    assert parse("control+option+a") == Combo(("ctrl", "alt"), "a")
    assert parse("command+a") == Combo(("win",), "a")


def test_parse_alias_keys():
    assert parse("ctrl+arrowleft").key == "left"
    assert parse("ctrl+esc").key == "escape"
    assert parse("ctrl+return").key == "enter"
    assert parse("ctrl+plus").key == "="


def test_parse_rejects_empty():
    with pytest.raises(ShortcutParseError):
        parse("")
    with pytest.raises(ShortcutParseError):
        parse("   ")


def test_parse_rejects_modifier_only():
    with pytest.raises(ShortcutParseError):
        parse("ctrl+alt")


def test_parse_rejects_two_non_modifier_keys():
    with pytest.raises(ShortcutParseError):
        parse("ctrl+a+b")


# ----- normalise() ---------------------------------------------------

def test_normalise_roundtrips():
    assert normalise("Ctrl+Alt+Left") == "ctrl+alt+left"
    assert normalise("Win+Shift+Alt+Ctrl+a") == "ctrl+alt+shift+win+a"


def test_normalise_idempotent():
    once = normalise("Ctrl+Alt+=")
    twice = normalise(once)
    assert once == twice


def test_normalise_different_typing_same_canonical():
    assert normalise("opt+ctrl+arrowleft") == normalise("control+alt+left")


# ----- conflicts() ---------------------------------------------------

def test_conflicts_detects_duplicates():
    result = conflicts({
        "left_half": "Ctrl+Alt+Left",
        "first_third": "ctrl+alt+left",  # canonically identical
        "right_half": "Ctrl+Alt+Right",
    })
    # Whichever key was first gets listed as the owner; the other is in the conflict list.
    assert any(
        ("left_half" in [owner] and "first_third" in clashers)
        or ("first_third" in [owner] and "left_half" in clashers)
        for owner, clashers in result.items()
    )
    # right_half has no conflicts → not in result.
    assert "right_half" not in result


def test_conflicts_empty_when_unique():
    assert conflicts({
        "a": "Ctrl+Alt+A",
        "b": "Ctrl+Alt+B",
    }) == {}


def test_conflicts_ignores_unparseable():
    # Unparseable entries are silently skipped (the prefs UI flags them separately).
    result = conflicts({
        "a": "Ctrl+Alt+A",
        "broken": "",
    })
    assert result == {}


# ----- is_reserved() -------------------------------------------------

@pytest.mark.parametrize("combo", ["win+left", "Win+Right", "WIN+UP", "alt+f4"])
def test_is_reserved_known_os_combos(combo):
    assert is_reserved(combo)


def test_is_reserved_normal_combo_not_reserved():
    assert not is_reserved("ctrl+alt+left")


def test_is_reserved_unparseable_is_false():
    assert not is_reserved("")
