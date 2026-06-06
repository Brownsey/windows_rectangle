"""Combo -> Win32 (modifier-mask, vkey) translation.

Pure constants + lookup table. No pywin32 dependency — the values are
the public Win32 numbers, so the eventual adapter just passes them
straight to `RegisterHotKey`.

Reference: https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
and https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey
"""

from __future__ import annotations

from .shortcuts import Combo


# --- Win32 RegisterHotKey modifier flags ---
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # OR'd in so holding the key doesn't auto-fire


_MOD_BITS = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


# --- Virtual-key codes ---
# Named keys + punctuation we bind by default. ASCII letters + digits are
# computed on the fly.
_NAMED_VKEYS: dict[str, int] = {
    "left":       0x25,  # VK_LEFT
    "up":         0x26,  # VK_UP
    "right":      0x27,  # VK_RIGHT
    "down":       0x28,  # VK_DOWN
    "enter":      0x0D,  # VK_RETURN
    "backspace":  0x08,  # VK_BACK
    "tab":        0x09,  # VK_TAB
    "escape":     0x1B,  # VK_ESCAPE
    "space":      0x20,  # VK_SPACE
    "delete":     0x2E,  # VK_DELETE
    "insert":     0x2D,  # VK_INSERT
    "home":       0x24,  # VK_HOME
    "end":        0x23,  # VK_END
    "pageup":     0x21,  # VK_PRIOR
    "pagedown":   0x22,  # VK_NEXT
    "=":          0xBB,  # VK_OEM_PLUS
    "-":          0xBD,  # VK_OEM_MINUS
    ",":          0xBC,  # VK_OEM_COMMA
    ".":          0xBE,  # VK_OEM_PERIOD
    "/":          0xBF,  # VK_OEM_2
    ";":          0xBA,  # VK_OEM_1
    "'":          0xDE,  # VK_OEM_7
    "[":          0xDB,  # VK_OEM_4
    "]":          0xDD,  # VK_OEM_6
    "\\":         0xDC,  # VK_OEM_5
    "`":          0xC0,  # VK_OEM_3
}

# F1..F24
for _i in range(1, 25):
    _NAMED_VKEYS[f"f{_i}"] = 0x70 + _i - 1  # VK_F1 = 0x70


class UnsupportedKeyError(ValueError):
    """Raised when the canonical key name has no Win32 vkey mapping."""


def vkey_for(key: str) -> int:
    """Translate a canonical key name (from shortcuts.Combo.key) to a VK_ code."""
    if key in _NAMED_VKEYS:
        return _NAMED_VKEYS[key]
    if len(key) == 1:
        ch = key.lower()
        if "a" <= ch <= "z":
            return 0x41 + (ord(ch) - ord("a"))  # VK_A..VK_Z
        if "0" <= ch <= "9":
            return 0x30 + (ord(ch) - ord("0"))  # VK_0..VK_9
    raise UnsupportedKeyError(f"no Win32 vkey for key {key!r}")


def modifier_mask(modifiers: tuple[str, ...], *, no_repeat: bool = True) -> int:
    """OR the modifier bits together. Defaults to `MOD_NOREPEAT` so holding
    a key doesn't repeat-fire the action.
    """
    mask = 0
    for m in modifiers:
        try:
            mask |= _MOD_BITS[m]
        except KeyError as e:
            raise UnsupportedKeyError(f"unknown modifier {m!r}") from e
    if no_repeat:
        mask |= MOD_NOREPEAT
    return mask


def translate(combo: Combo, *, no_repeat: bool = True) -> tuple[int, int]:
    """Top-level: combo -> (mod_mask, vkey) ready for RegisterHotKey."""
    return modifier_mask(combo.modifiers, no_repeat=no_repeat), vkey_for(combo.key)
