"""Tests for windows_rectangle.core.actionbus."""

import threading

from windows_rectangle.core.actionbus import ActionBus
from windows_rectangle.core.actions import Action


def test_submit_and_drain_roundtrip():
    bus = ActionBus()
    bus.submit(Action.LEFT_HALF)
    bus.submit(Action.RIGHT_HALF)

    seen = []
    drained = bus.drain(seen.append)
    assert drained == 2
    assert seen == [Action.LEFT_HALF, Action.RIGHT_HALF]


def test_drain_can_be_limited():
    bus = ActionBus()
    bus.submit(Action.LEFT_HALF)
    bus.submit(Action.RIGHT_HALF)
    bus.submit(Action.MAXIMIZE)

    seen = []
    drained = bus.drain(seen.append, max_items=2)

    assert drained == 2
    assert seen == [Action.LEFT_HALF, Action.RIGHT_HALF]
    assert bus.pending() == 1


def test_drain_empty_returns_zero():
    assert ActionBus().drain(lambda a: None) == 0


def test_pending_reflects_queue_size():
    bus = ActionBus()
    assert bus.pending() == 0
    bus.submit(Action.MAXIMIZE)
    assert bus.pending() == 1
    bus.drain(lambda a: None)
    assert bus.pending() == 0


def test_submit_does_not_block_when_full():
    bus = ActionBus(maxsize=2)
    assert bus.submit(Action.LEFT_HALF) is True
    assert bus.submit(Action.RIGHT_HALF) is True
    # Overflow — should return False but not raise/block.
    assert bus.submit(Action.MAXIMIZE) is False
    # Newest action survived; oldest dropped.
    seen = []
    bus.drain(seen.append)
    assert Action.LEFT_HALF not in seen
    assert Action.MAXIMIZE in seen


def test_handler_exception_doesnt_stop_drain():
    bus = ActionBus()
    bus.submit(Action.LEFT_HALF)
    bus.submit(Action.RIGHT_HALF)
    seen = []

    def handler(action):
        if action == Action.LEFT_HALF:
            raise RuntimeError("boom")
        seen.append(action)

    drained = bus.drain(handler)
    assert drained == 2
    assert seen == [Action.RIGHT_HALF]


def test_concurrent_producers_all_actions_arrive():
    bus = ActionBus(maxsize=0)  # unbounded
    PRODUCERS = 8
    PER = 50

    def produce():
        for _ in range(PER):
            bus.submit(Action.CENTER)

    threads = [threading.Thread(target=produce) for _ in range(PRODUCERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    seen = []
    bus.drain(seen.append)
    assert len(seen) == PRODUCERS * PER
    assert all(a is Action.CENTER for a in seen)


def test_producer_thread_drained_by_main_thread():
    """End-to-end: a worker thread submits while the main thread drains."""
    bus = ActionBus()
    seen = []
    submitted = 0

    def worker():
        nonlocal submitted
        for _ in range(20):
            bus.submit(Action.LARGER)
            submitted += 1

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    bus.drain(seen.append)
    assert submitted == 20
    assert len(seen) == 20


def test_trim_to_latest_drops_oldest_actions():
    bus = ActionBus()
    bus.submit(Action.LEFT_HALF)
    bus.submit(Action.RIGHT_HALF)
    bus.submit(Action.MAXIMIZE)
    bus.submit(Action.CENTER)

    assert bus.trim_to_latest(2) == 2

    seen = []
    bus.drain(seen.append)
    assert seen == [Action.MAXIMIZE, Action.CENTER]


def test_trim_to_latest_rejects_negative_limit():
    bus = ActionBus()

    try:
        bus.trim_to_latest(-1)
    except ValueError as exc:
        assert "max_pending" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("negative trim limit should fail")
