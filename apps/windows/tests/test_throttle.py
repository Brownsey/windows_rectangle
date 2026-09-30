"""Tests for windows_rectangle.core.throttle."""

import threading

from windows_rectangle.core.throttle import LatestValue, Throttle


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


# ----- Throttle -------------------------------------------------------


def test_throttle_first_call_runs():
    clk = FakeClock()
    th = Throttle(interval=0.05, _clock=clk)
    assert th.should_run()


def test_throttle_blocks_within_interval():
    clk = FakeClock()
    th = Throttle(interval=0.05, _clock=clk)
    th.should_run()
    clk.advance(0.01)
    assert not th.should_run()


def test_throttle_allows_after_interval():
    clk = FakeClock()
    th = Throttle(interval=0.05, _clock=clk)
    th.should_run()
    clk.advance(0.05)
    assert th.should_run()


def test_throttle_reset_re_arms():
    clk = FakeClock()
    th = Throttle(interval=0.05, _clock=clk)
    th.should_run()
    th.reset()
    assert th.should_run()


# ----- LatestValue ---------------------------------------------------


def test_latest_value_set_and_pop():
    lv: LatestValue[int] = LatestValue()
    assert not lv.has_value
    lv.set(7)
    assert lv.has_value
    assert lv.pop() == 7
    assert lv.pop() is None


def test_latest_value_overwrites_intermediate():
    lv: LatestValue[tuple[int, int]] = LatestValue()
    lv.set((1, 2))
    lv.set((3, 4))
    lv.set((5, 6))
    # Only the newest survives.
    assert lv.pop() == (5, 6)


def test_latest_value_peek_doesnt_clear():
    lv: LatestValue[str] = LatestValue()
    lv.set("hi")
    assert lv.peek() == "hi"
    assert lv.peek() == "hi"  # still there
    assert lv.pop() == "hi"
    assert lv.peek() is None


def test_latest_value_threaded_producers():
    """Many writes, single read — newest write must be observable."""
    lv: LatestValue[int] = LatestValue()

    def writer(n):
        for i in range(100):
            lv.set(n * 1000 + i)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # We can't predict the exact value (race), but a value must be present.
    assert lv.has_value
    final = lv.pop()
    assert final is not None
    # No exceptions raised, slot cleared.
    assert lv.pop() is None


def test_latest_value_preserves_write_during_pop():
    """A producer write between read and clear must remain available."""
    read_started = threading.Event()
    resume_read = threading.Event()
    consumed: list[int | None] = []
    reader_ident: int | None = None

    class PausedRead(LatestValue[int]):
        def __getattribute__(self, name):
            value = super().__getattribute__(name)
            if name in ("_value", "_values") and threading.get_ident() == reader_ident:
                read_started.set()
                assert resume_read.wait(timeout=2)
            return value

    lv = PausedRead(1)

    def consume():
        nonlocal reader_ident
        reader_ident = threading.get_ident()
        consumed.append(lv.pop())

    reader = threading.Thread(target=consume)
    writer = threading.Thread(target=lambda: lv.set(2))
    reader.start()
    assert read_started.wait(timeout=2)
    writer.start()
    writer.join(timeout=2)
    assert not writer.is_alive()
    resume_read.set()
    reader.join(timeout=2)
    assert not reader.is_alive()
    assert consumed[0] == 2 or lv.pop() == 2
