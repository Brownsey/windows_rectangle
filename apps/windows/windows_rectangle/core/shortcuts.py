"""Keyboard shortcut combo parsing and normalisation.

User-facing combos are typed many ways:
- "Ctrl+Alt+Left", "control + alt + LEFT", "ctrl-alt-left"

We canonicalise them to a single form so we can:
1. Spot duplicates when the user rebinds a shortcut (brief §5.5).
2. Round-trip cleanly through JSON config without case noise.
3. Hand the adapter a clean (modifier-mask, vkey-name) pair.
"""

from __future__ import annotations

from dataclasses import dataclass


class ShortcutParseError(ValueError):
    """Raised when a combo string can't be parsed."""


# Canonical modifier order — Rectangle convention + Windows convention.
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctl": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
    "super": "win",
    "meta": "win",
    "cmd": "win",
    "command": "win",
}

# Canonical key-name aliases.
_KEY_ALIASES = {
    "arrowleft": "left",
    "arrowright": "right",
    "arrowup": "up",
    "arrowdown": "down",
    "esc": "escape",
    "return": "enter",
    "del": "delete",
    "ins": "insert",
    "bksp": "backspace",
    "backsp": "backspace",
    "plus": "=",
    "minus": "-",
    "equals": "=",
    "equal": "=",
    "spacebar": "space",
}


@dataclass(frozen=True, slots=True)
class Combo:
    """A parsed, canonical key combination."""

    modifiers: tuple[str, ...]  # always in _MODIFIER_ORDER
    key: str  # canonical key name (lowercase)

    def __str__(self) -> str:
        return "+".join(self.modifiers + (self.key,))

    @property
    def is_modifier_only(self) -> bool:
        return self.key in _MODIFIER_ALIASES


def parse(combo: str) -> Combo:
    """Parse a user-supplied combo string. Case-insensitive, `+`-separated.

    `-` is *not* a separator because `-` is itself a bindable key
    (e.g. Rectangle's "smaller" action is `Ctrl+Alt+-`).
    """
    if not combo or not combo.strip():
        raise ShortcutParseError("empty combo")
    raw = combo.strip().lower()
    # Split on `+` but preserve a trailing/standalone `-` token (the minus key).
    tokens = [t.strip() for t in raw.split("+") if t.strip()]
    if not tokens:
        raise ShortcutParseError(f"no tokens in {combo!r}")

    mods: set[str] = set()
    key: str | None = None
    for tok in tokens:
        if tok in _MODIFIER_ALIASES:
            mods.add(_MODIFIER_ALIASES[tok])
        else:
            if key is not None:
                raise ShortcutParseError(
                    f"more than one non-modifier key in {combo!r}: {key!r} and {tok!r}"
                )
            key = _KEY_ALIASES.get(tok, tok)

    if key is None:
        raise ShortcutParseError(f"combo {combo!r} has no non-modifier key")

    ordered_mods = tuple(m for m in _MODIFIER_ORDER if m in mods)
    return Combo(modifiers=ordered_mods, key=key)


def normalise(combo: str) -> str:
    """Convenience: `str(parse(combo))`. Stable string for comparison."""
    return str(parse(combo))


def conflicts(combos: dict[str, str]) -> dict[str, list[str]]:
    """Return action -> list-of-other-actions that share the same canonical combo.

    `combos` is `{action_name: combo_string}`. Used by the prefs UI to flag
    duplicate bindings before saving.
    """
    by_canonical: dict[str, list[str]] = {}
    for name, combo in combos.items():
        try:
            canon = normalise(combo)
        except ShortcutParseError:
            continue
        by_canonical.setdefault(canon, []).append(name)
    return {names[0]: names[1:] for names in by_canonical.values() if len(names) > 1}


# Combos the user is allowed to *bind* but should be warned about — they
# clash with the OS or other well-known shortcuts. Brief §2 calls out
# Win+arrow as reserved by Windows Snap.
RESERVED_COMBOS: frozenset[str] = frozenset(
    {
        "win+left",
        "win+right",
        "win+up",
        "win+down",
        "alt+f4",
        "alt+tab",
        "ctrl+alt+delete",
    }
)


def is_reserved(combo: str) -> bool:
    """True if `combo` clashes with a known OS-reserved shortcut."""
    try:
        canon = normalise(combo)
    except ShortcutParseError:
        return False
    return canon in RESERVED_COMBOS
