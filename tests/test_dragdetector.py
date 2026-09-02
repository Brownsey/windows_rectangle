"""Tests for windows_rectangle.core.dragdetector.

Drives the state machine through realistic event sequences and asserts
on which callbacks fire and in what order. Pure-Python — no win32.
"""

from windows_rectangle.core.dragdetector import (
    DEFAULT_DRAG_THRESHOLD_PX,
    DragDetector,
)


class _Recorder:
    """Captures callback invocations with their args, in order."""

    def __init__(self, begin_returns: bool = True) -> None:
        self.events: list[tuple[str, tuple]] = []
        self.begin_returns = begin_returns

    def begin(self, x, y):
        self.events.append(("begin", (x, y)))
        return self.begin_returns

    def update(self, x, y):
        self.events.append(("update", (x, y)))

    def end(self):
        self.events.append(("end", ()))


def _make(begin_returns: bool = True, threshold: int = DEFAULT_DRAG_THRESHOLD_PX):
    r = _Recorder(begin_returns=begin_returns)
    d = DragDetector(
        on_begin=r.begin,
        on_update=r.update,
        on_end=r.end,
        threshold_px=threshold,
    )
    return d, r


def test_starts_idle():
    d, _ = _make()
    assert d.state == "idle"


def test_button_down_arms_without_begin():
    d, r = _make()
    d.on_button_down(100, 100)
    assert d.state == "armed"
    assert r.events == []  # no begin yet — waiting for threshold


def test_below_threshold_move_stays_armed():
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_move(102, 102)  # dist² = 8 < 25
    assert d.state == "armed"
    assert r.events == []


def test_crossing_threshold_triggers_begin_and_update():
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_move(110, 110)  # dist² = 200 > 25
    assert d.state == "dragging"
    assert r.events == [("begin", (110, 110)), ("update", (110, 110))]


def test_dragging_moves_only_emit_update():
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_move(110, 110)  # begin + update
    d.on_move(120, 130)
    d.on_move(200, 200)
    assert r.events[-2:] == [("update", (120, 130)), ("update", (200, 200))]


def test_button_up_after_drag_fires_end():
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_move(110, 110)
    d.on_button_up(110, 110)
    assert d.state == "idle"
    assert ("end", ()) in r.events
    assert r.events[-1] == ("end", ())


def test_click_without_drag_does_not_fire_end():
    """LBUTTON_DOWN + LBUTTON_UP with no movement past threshold == a click,
    not a drag → no begin and no end."""
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_button_up(101, 101)
    assert d.state == "idle"
    assert r.events == []


def test_begin_callback_rejection_drops_to_idle():
    """If on_begin returns False (foreground window not eligible), the
    detector resets to IDLE so a later LBUTTON_UP isn't mis-routed."""
    d, r = _make(begin_returns=False, threshold=5)
    d.on_button_down(100, 100)
    d.on_move(120, 120)
    assert d.state == "idle"
    assert r.events == [("begin", (120, 120))]
    # Subsequent up: must not fire end.
    d.on_button_up(120, 120)
    assert r.events == [("begin", (120, 120))]


def test_move_without_button_down_is_noop():
    d, r = _make()
    d.on_move(500, 500)
    assert d.state == "idle"
    assert r.events == []


def test_reset_returns_to_idle_without_firing_end():
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_move(120, 120)
    assert d.state == "dragging"
    d.reset()
    assert d.state == "idle"
    # Last event should be the update from the drag, not an end.
    assert r.events[-1] != ("end", ())


def test_redundant_button_down_just_rearms():
    """Some hooks deliver duplicate LBUTTON_DOWN events (e.g. fast tablet
    pen taps). Re-anchoring is fine; no spurious begin should fire."""
    d, r = _make(threshold=5)
    d.on_button_down(100, 100)
    d.on_button_down(200, 200)
    assert d.state == "armed"
    # Now move from the new anchor.
    d.on_move(220, 220)
    assert d.state == "dragging"
    assert r.events[0] == ("begin", (220, 220))
