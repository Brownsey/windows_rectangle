"""Rate-limit and latest-value helpers for bounded polling work."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

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
    """Single-slot handoff for producers and one consumer.

    Deque append/pop operations are atomic on CPython. Producers overwrite
    older values; a consumer pop cannot erase a value appended afterward.
    """

    __slots__ = ("_values",)

    def __init__(self, initial: T | None = None) -> None:
        self._values: deque[T] = deque(maxlen=1)
        if initial is not None:
            self._values.append(initial)

    def set(self, value: T) -> None:
        self._values.append(value)

    def pop(self) -> T | None:
        """Take the latest value and clear the slot. None if empty."""
        try:
            return self._values.pop()
        except IndexError:
            return None

    def peek(self) -> T | None:
        try:
            return self._values[-1]
        except IndexError:
            return None

    @property
    def has_value(self) -> bool:
        return bool(self._values)
