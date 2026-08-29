"""Tests for windows_rectangle.core.history."""

from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.history import History

R1 = Rect(0, 0, 100, 100)
R2 = Rect(10, 10, 200, 200)
R3 = Rect(20, 20, 300, 300)


def test_push_and_pop_lifo():
    h = History()
    h.push(1, R1)
    h.push(1, R2)
    h.push(1, R3)
    assert h.pop(1) == R3
    assert h.pop(1) == R2
    assert h.pop(1) == R1
    assert h.pop(1) is None


def test_pop_empty_returns_none():
    assert History().pop(42) is None


def test_peek_doesnt_consume():
    h = History()
    h.push(1, R1)
    assert h.peek(1) == R1
    assert h.peek(1) == R1
    assert h.pop(1) == R1


def test_duplicate_top_not_pushed():
    h = History()
    h.push(1, R1)
    h.push(1, R1)
    h.push(1, R1)
    assert h.pop(1) == R1
    assert h.pop(1) is None


def test_per_window_independent():
    h = History()
    h.push(1, R1)
    h.push(2, R2)
    assert h.pop(1) == R1
    assert h.pop(2) == R2


def test_max_per_window_caps_stack():
    h = History(max_per_window=2)
    h.push(1, R1)
    h.push(1, R2)
    h.push(1, R3)  # R1 evicted
    assert h.pop(1) == R3
    assert h.pop(1) == R2
    assert h.pop(1) is None


def test_evict():
    h = History()
    h.push(1, R1)
    h.evict(1)
    assert h.pop(1) is None


def test_prune_stale_drops_dead_windows():
    h = History()
    h.push(1, R1)
    h.push(2, R2)
    dropped = h.prune_stale(is_alive=lambda wid: wid == 1)
    assert dropped == 1
    assert h.pop(1) == R1
    assert h.pop(2) is None


def test_len_counts_all_entries():
    h = History()
    h.push(1, R1)
    h.push(1, R2)
    h.push(2, R3)
    assert len(h) == 3
