"""Tests for windows_rectangle.core.cycle."""

from windows_rectangle.core.actions import Action
from windows_rectangle.core.cycle import CycleState


class FakeClock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_state(timeout: float = 1.5) -> tuple[CycleState, FakeClock]:
    clk = FakeClock()
    return CycleState(idle_timeout=timeout, _clock=clk), clk


def test_first_press_returns_requested():
    state, _ = make_state()
    assert state.next_action(1, Action.LEFT_HALF) == Action.LEFT_HALF


def test_repeat_press_within_timeout_cycles():
    state, clk = make_state()
    assert state.next_action(1, Action.LEFT_HALF) == Action.LEFT_HALF
    clk.advance(0.5)
    assert state.next_action(1, Action.LEFT_HALF) == Action.FIRST_THIRD
    clk.advance(0.5)
    assert state.next_action(1, Action.LEFT_HALF) == Action.FIRST_TWO_THIRDS
    clk.advance(0.5)
    # Wraps.
    assert state.next_action(1, Action.LEFT_HALF) == Action.LEFT_HALF


def test_idle_timeout_resets():
    state, clk = make_state(timeout=1.0)
    state.next_action(1, Action.LEFT_HALF)
    clk.advance(2.0)
    assert state.next_action(1, Action.LEFT_HALF) == Action.LEFT_HALF


def test_per_window_independent():
    state, clk = make_state()
    state.next_action(1, Action.LEFT_HALF)
    clk.advance(0.1)
    # Window 2's first press should still be LEFT_HALF.
    assert state.next_action(2, Action.LEFT_HALF) == Action.LEFT_HALF


def test_non_cycling_action_returns_itself():
    state, _ = make_state()
    # MAXIMIZE has no cycle group.
    assert state.next_action(1, Action.MAXIMIZE) == Action.MAXIMIZE


def test_right_half_cycle():
    state, clk = make_state()
    assert state.next_action(7, Action.RIGHT_HALF) == Action.RIGHT_HALF
    clk.advance(0.1)
    assert state.next_action(7, Action.RIGHT_HALF) == Action.LAST_THIRD


def test_evict_clears_state():
    state, clk = make_state()
    state.next_action(99, Action.LEFT_HALF)
    state.evict(99)
    clk.advance(0.1)
    assert state.next_action(99, Action.LEFT_HALF) == Action.LEFT_HALF


def test_prune_stale_drops_dead_windows():
    state, _ = make_state()
    state.next_action(1, Action.LEFT_HALF)
    state.next_action(2, Action.RIGHT_HALF)
    dropped = state.prune_stale(is_alive=lambda wid: wid == 1)
    assert dropped == 1
    # Window 1 retained.
    assert (1, (Action.LEFT_HALF, Action.FIRST_THIRD, Action.FIRST_TWO_THIRDS)) in state._entries
