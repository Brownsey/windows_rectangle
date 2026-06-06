"""Tests for windows_rectangle.core.eligibility."""

from windows_rectangle.core.eligibility import (
    Capability,
    WindowFlags,
    classify,
    is_eligible,
)


def normal_window() -> WindowFlags:
    """A standard top-level resizable window."""
    return WindowFlags(has_caption=True, has_thick_frame=True)


def test_normal_window_is_move_and_resize():
    assert classify(normal_window()) is Capability.MOVE_AND_RESIZE
    assert is_eligible(normal_window())


def test_fixed_size_window_is_move_only():
    flags = WindowFlags(has_caption=True, has_thick_frame=False)
    assert classify(flags) is Capability.MOVE
    assert is_eligible(flags)


def test_tool_window_rejected():
    flags = WindowFlags(has_caption=True, has_thick_frame=True, is_tool_window=True)
    assert classify(flags) is Capability.NONE
    assert not is_eligible(flags)


def test_shell_window_rejected():
    flags = WindowFlags(has_caption=True, has_thick_frame=True, is_shell_window=True)
    assert classify(flags) is Capability.NONE


def test_cloaked_window_rejected():
    flags = WindowFlags(has_caption=True, has_thick_frame=True, is_cloaked=True)
    assert classify(flags) is Capability.NONE


def test_minimized_window_rejected():
    flags = WindowFlags(has_caption=True, has_thick_frame=True, is_minimized=True)
    assert classify(flags) is Capability.NONE


def test_disabled_window_rejected():
    flags = WindowFlags(has_caption=True, has_thick_frame=True, is_disabled=True)
    assert classify(flags) is Capability.NONE


def test_caption_required():
    # No caption → desktop / popup-style window; skip.
    flags = WindowFlags(has_caption=False, has_thick_frame=True)
    assert classify(flags) is Capability.NONE


def test_can_check_capability_with_bitwise_and():
    cap = classify(normal_window())
    assert Capability.MOVE in cap
    assert Capability.RESIZE in cap

    move_only = classify(WindowFlags(has_caption=True, has_thick_frame=False))
    assert Capability.MOVE in move_only
    assert Capability.RESIZE not in move_only
