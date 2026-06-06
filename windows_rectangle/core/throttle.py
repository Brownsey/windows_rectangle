"""Rate-limit + latest-value helpers (brief §5 #7).

The `WH_MOUSE_LL` hook must return fast or Windows drops it. Pattern:
    - Hook stores the cursor coords into a `LatestValue` (O(1), no I/O).
    - A polling timer reads the latest value at ~60 Hz (`Throttle`) and
      does the snap-zone + overlay work off the hook thread.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(slots=True)
class Throttle:
    """Allow at most one accepted call every `interval` seconds.

    Clock is injectable for tests.
    """

    interval: float
    _last: float = float("-inf")
    _clock: Callable[[], float] = field(default=time.monotonic)

    def should_run(self) -> bool:
        """True iff at least `interval` seconds elapsed since the last accept."""
        now = self._clock()
        if now - self._last >= self.interval:
            self._last = now
            return True
        return False

    def reset(self) -> None:
        self._last = float("-inf")


class LatestValue(Generic[T]):
    """Single-slot lock-free-ish latest-value latch.

    Producers overwrite the slot atomically (Python assignment is
    GIL-atomic for object refs). The consumer takes the value with
    `pop()`, which atomically clears the slot. No queueing — older
    writes are silently dropped, which is exactly what the mouse hook
    needs (we only care about the most recent cursor position).
    """

    __slots__ = ("_value", "_lock")

    def __init__(self, initial: T | None = None) -> None:
        self._value: T | None = initial
        # The lock guards the pop-and-clear pair, not the assignment.
        self._lock = threading.Lock()

    def set(self, value: T) -> None:
        self._value = value

    def pop(self) -> T | None:
        """Take the latest value and clear the slot. None if empty."""
        with self._lock:
            v = self._value
            self._value = None
            return v

    def peek(self) -> T | None:
        return self._value

    @property
    def has_value(self) -> bool:
        return self._value is not None
