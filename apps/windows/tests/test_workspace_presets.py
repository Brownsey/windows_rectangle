"""Tests for user-facing workspace position presets."""

import pytest
from windows_rectangle.core.workspace_presets import (
    POSITION_PRESETS,
    preset_label,
    preset_rect,
)
from windows_rectangle.core.workspaces import NormalizedRect


def test_preset_ids_are_unique_and_have_valid_rectangles():
    assert len({preset.id for preset in POSITION_PRESETS}) == len(POSITION_PRESETS)
    assert all(isinstance(preset.rect, NormalizedRect) for preset in POSITION_PRESETS)


def test_preset_lookup_and_custom_label():
    assert preset_rect("top_left") == NormalizedRect(0, 0, 5000, 5000)
    assert preset_label(preset_rect("right_half")) == "Right half"
    assert preset_label(NormalizedRect(100, 200, 9000, 9500)) == "Custom"


def test_unknown_preset_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown position preset"):
        preset_rect("diagonal")
