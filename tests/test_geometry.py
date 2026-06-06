"""Tests for windows_rectangle.core.geometry."""

from fractions import Fraction

import pytest

from windows_rectangle.core.geometry import (
    EdgeFlags,
    Rect,
    apply_gap,
    apply_relative_position,
    fraction_rect,
    relative_position,
    tile_edges,
    union,
)


WORK = Rect(0, 0, 1920, 1080)


# ----- Rect basics ----------------------------------------------------

def test_from_ltrb_roundtrips():
    r = Rect.from_ltrb(10, 20, 110, 220)
    assert (r.left, r.top, r.right, r.bottom) == (10, 20, 110, 220)
    assert (r.width, r.height) == (100, 200)


def test_area_and_empty():
    assert Rect(0, 0, 100, 50).area == 5000
    assert Rect(0, 0, 0, 50).is_empty()
    assert Rect(0, 0, 100, 0).is_empty()


def test_with_gap_no_op_for_non_positive():
    r = Rect(0, 0, 100, 100)
    assert r.with_gap(0) is r
    assert r.with_gap(-5) is r


def test_with_gap_insets_evenly():
    r = Rect(0, 0, 100, 100).with_gap(10)
    assert r == Rect(10, 10, 80, 80)


def test_clamp_to_inside_bounds():
    inner = Rect(50, 50, 100, 100)
    assert inner.clamp_to(WORK) == inner


def test_clamp_to_clips_overflow():
    r = Rect(-10, -10, 200, 200).clamp_to(Rect(0, 0, 150, 150))
    assert r == Rect(0, 0, 150, 150)


def test_clamp_to_completely_outside():
    r = Rect(2000, 2000, 100, 100).clamp_to(WORK)
    assert r.is_empty()


def test_scaled_keeps_center_close():
    r = Rect(0, 0, 100, 100).scaled(0.5)
    assert (r.width, r.height) == (50, 50)
    assert abs(r.center_x - 50) <= 1
    assert abs(r.center_y - 50) <= 1


def test_centered_in_doesnt_resize():
    r = Rect(0, 0, 200, 100).centered_in(WORK)
    assert (r.width, r.height) == (200, 100)
    assert r.center_x == WORK.center_x
    assert r.center_y == WORK.center_y


# ----- fraction_rect --------------------------------------------------

def test_fraction_rect_full_area():
    assert fraction_rect(WORK) == WORK


def test_fraction_rect_left_half():
    r = fraction_rect(WORK, right=Fraction(1, 2))
    assert r == Rect(0, 0, 960, 1080)


def test_fraction_rect_right_half_meets_left_half():
    left = fraction_rect(WORK, right=Fraction(1, 2))
    right = fraction_rect(WORK, left=Fraction(1, 2))
    assert left.right == right.left  # no overlap, no gap


def test_fraction_rect_thirds_partition_work_area_exactly():
    a = fraction_rect(WORK, right=Fraction(1, 3))
    b = fraction_rect(WORK, left=Fraction(1, 3), right=Fraction(2, 3))
    c = fraction_rect(WORK, left=Fraction(2, 3))
    assert a.right == b.left
    assert b.right == c.left
    assert a.left == WORK.left and c.right == WORK.right


def test_fraction_rect_rejects_inverted():
    with pytest.raises(ValueError):
        fraction_rect(WORK, left=0.5, right=0.4)
    with pytest.raises(ValueError):
        fraction_rect(WORK, top=-0.1)


# ----- tile_edges + apply_gap ----------------------------------------

def test_tile_edges_left_half():
    edges = tile_edges(0, 0, Fraction(1, 2), 1)
    assert edges == EdgeFlags(left=False, top=False, right=True, bottom=False)


def test_tile_edges_top_left_quarter():
    edges = tile_edges(0, 0, Fraction(1, 2), Fraction(1, 2))
    assert edges == EdgeFlags(left=False, top=False, right=True, bottom=True)


def test_apply_gap_shrinks_outer_edges_full():
    tile = fraction_rect(WORK)
    edges = tile_edges(0, 0, 1, 1)
    out = apply_gap(WORK, tile, edges, 10)
    # All edges touch the work area boundary → full gap inset on each side.
    assert out == Rect(10, 10, 1900, 1060)


def test_apply_gap_shrinks_half_gap_between_tiles():
    # Two left/right halves with gap=10 leave a 10-px gutter.
    left_tile = fraction_rect(WORK, right=Fraction(1, 2))
    right_tile = fraction_rect(WORK, left=Fraction(1, 2))
    gl = apply_gap(WORK, left_tile, tile_edges(0, 0, Fraction(1, 2), 1), 10)
    gr = apply_gap(WORK, right_tile, tile_edges(Fraction(1, 2), 0, 1, 1), 10)
    assert gr.left - gl.right == 10
    # Outer edges still inset by full gap.
    assert gl.left == 10
    assert gr.right == WORK.width - 10


def test_apply_gap_no_op_for_zero():
    tile = Rect(0, 0, 100, 100)
    assert apply_gap(WORK, tile, EdgeFlags(), 0) == tile


# ----- union ----------------------------------------------------------

def test_union_empty():
    assert union([]) == Rect(0, 0, 0, 0)


def test_union_two_monitors():
    m1 = Rect(0, 0, 1920, 1080)
    m2 = Rect(1920, 100, 1920, 1080)
    u = union([m1, m2])
    assert u == Rect(0, 0, 3840, 1180)


# ----- relative_position roundtrip -----------------------------------

def test_relative_position_roundtrip_exact():
    win = Rect(480, 270, 480, 540)  # left-quarter, vertically centered
    mon = Rect(0, 0, 1920, 1080)
    fracs = relative_position(win, mon)
    out = apply_relative_position(fracs, mon)
    assert out == win


def test_relative_position_preserves_fractions_across_monitors():
    win = Rect(960, 0, 960, 1080)  # right half of mon1
    mon1 = Rect(0, 0, 1920, 1080)
    mon2 = Rect(2000, 100, 1280, 720)
    fracs = relative_position(win, mon1)
    out = apply_relative_position(fracs, mon2)
    # Right half of mon2.
    assert out == Rect(2000 + 640, 100, 640, 720)
