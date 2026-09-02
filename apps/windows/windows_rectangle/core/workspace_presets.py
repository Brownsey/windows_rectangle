"""Named normalized regions used by the workspace setup UI."""

from __future__ import annotations

from dataclasses import dataclass

from .workspaces import BASIS, NormalizedRect


@dataclass(frozen=True, slots=True)
class PositionPreset:
    id: str
    label: str
    rect: NormalizedRect


def _rect(left: int, top: int, right: int, bottom: int) -> NormalizedRect:
    return NormalizedRect(left, top, right, bottom)


POSITION_PRESETS: tuple[PositionPreset, ...] = (
    PositionPreset("full", "Full screen", _rect(0, 0, BASIS, BASIS)),
    PositionPreset("left_half", "Left half", _rect(0, 0, 5000, BASIS)),
    PositionPreset("right_half", "Right half", _rect(5000, 0, BASIS, BASIS)),
    PositionPreset("top_half", "Top half", _rect(0, 0, BASIS, 5000)),
    PositionPreset("bottom_half", "Bottom half", _rect(0, 5000, BASIS, BASIS)),
    PositionPreset("top_left", "Top-left quarter", _rect(0, 0, 5000, 5000)),
    PositionPreset("top_right", "Top-right quarter", _rect(5000, 0, BASIS, 5000)),
    PositionPreset("bottom_left", "Bottom-left quarter", _rect(0, 5000, 5000, BASIS)),
    PositionPreset("bottom_right", "Bottom-right quarter", _rect(5000, 5000, BASIS, BASIS)),
    PositionPreset("left_third", "Left third", _rect(0, 0, 3333, BASIS)),
    PositionPreset("center_third", "Center third", _rect(3333, 0, 6667, BASIS)),
    PositionPreset("right_third", "Right third", _rect(6667, 0, BASIS, BASIS)),
    PositionPreset("left_two_thirds", "Left two-thirds", _rect(0, 0, 6667, BASIS)),
    PositionPreset("right_two_thirds", "Right two-thirds", _rect(3333, 0, BASIS, BASIS)),
)

_BY_ID = {preset.id: preset for preset in POSITION_PRESETS}


def preset_rect(preset_id: str) -> NormalizedRect:
    try:
        return _BY_ID[preset_id].rect
    except KeyError as exc:
        raise ValueError(f"unknown position preset: {preset_id}") from exc


def preset_label(rect: NormalizedRect) -> str:
    for preset in POSITION_PRESETS:
        if preset.rect == rect:
            return preset.label
    return "Custom"
