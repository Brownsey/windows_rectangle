"""Tests for windows_rectangle.core.dragsession."""

from windows_rectangle.core.dragsession import DragSession
from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.snap import SnapZone

from .conftest import make_monitor


M1 = make_monitor(1, 0, 0, 1920, 1080, primary=True)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def make_session(monitors=(M1,), gap=0):
    clk = FakeClock()
    s = DragSession(monitors=list(monitors), gap=gap, poll_interval=0.016, _clock=clk)
    return s, clk


# ----- lifecycle ------------------------------------------------------

def test_inactive_before_start():
    s, _ = make_session()
    assert not s.active
    assert s.poll() is None


def test_start_activates():
    s, _ = make_session()
    s.start(Rect(100, 100, 800, 600))
    assert s.active


def test_finish_deactivates_and_returns_last_hit():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)
    clk.advance(1.0)
    s.poll()  # caches LEFT hit
    final = s.finish()
    assert final is not None
    assert final.zone is SnapZone.LEFT
    assert not s.active


def test_finish_with_no_hit_returns_none():
    s, _ = make_session()
    s.start(Rect(100, 100, 800, 600))
    assert s.finish() is None


# ----- update + poll --------------------------------------------------

def test_poll_with_no_coords_returns_none():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    clk.advance(1.0)
    assert s.poll() is None


def test_poll_uses_latest_coords():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(960, 540)   # center — would be NONE
    s.update(2, 540)     # left edge — overwrites
    clk.advance(1.0)
    hit = s.poll()
    assert hit is not None
    assert hit.zone is SnapZone.LEFT


def test_throttle_returns_cached_hit():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)
    clk.advance(1.0)
    first = s.poll()
    # Second poll immediately: throttle blocks, returns cached.
    assert s.poll() is first


def test_throttle_allows_after_interval():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)
    clk.advance(0.02)
    s.poll()
    s.update(1920 - 2, 540)  # right edge
    clk.advance(0.02)
    hit = s.poll()
    assert hit is not None
    assert hit.zone is SnapZone.RIGHT


def test_poll_no_zone_clears_last_hit():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)  # LEFT
    clk.advance(1.0)
    assert s.poll().zone is SnapZone.LEFT
    s.update(960, 540)  # center — NONE
    clk.advance(1.0)
    assert s.poll() is None


# ----- safety --------------------------------------------------------

def test_update_when_inactive_is_noop():
    s, _ = make_session()
    s.update(10, 10)
    assert s.poll() is None


def test_cancel_clears_state():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)
    clk.advance(1.0)
    s.poll()
    s.cancel()
    assert not s.active
    assert s.poll() is None


def test_start_resets_previous_state():
    s, clk = make_session()
    s.start(Rect(100, 100, 800, 600))
    s.update(2, 540)
    clk.advance(1.0)
    s.poll()
    # New drag starts fresh.
    s.start(Rect(0, 0, 200, 200))
    assert s.poll() is None
