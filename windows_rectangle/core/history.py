"""Per-window undo stack — the engine behind `Action.RESTORE`.

Stores the pre-action rect for each window. Validates HWND liveness via
an injected callback to avoid stale entries (brief §5.9).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Hashable

from .geometry import Rect


@dataclass(slots=True)
class History:
    """A bounded per-window undo stack."""

    max_per_window: int = 16
    _stacks: dict[Hashable, deque[Rect]] = field(default_factory=dict)

    def push(self, window_id: Hashable, rect: Rect) -> None:
        """Record `rect` as the pre-action position of `window_id`.

        No-op if the new rect equals the top of the stack — avoids
        pushing duplicates when the user repeats a no-op action.
        """
        stack = self._stacks.get(window_id)
        if stack is None:
            stack = deque(maxlen=self.max_per_window)
            self._stacks[window_id] = stack
        if stack and stack[-1] == rect:
            return
        stack.append(rect)

    def pop(self, window_id: Hashable) -> Rect | None:
        """Return the most recent pre-action rect, or None if empty."""
        stack = self._stacks.get(window_id)
        if not stack:
            return None
        rect = stack.pop()
        if not stack:
            del self._stacks[window_id]
        return rect

    def peek(self, window_id: Hashable) -> Rect | None:
        stack = self._stacks.get(window_id)
        return stack[-1] if stack else None

    def evict(self, window_id: Hashable) -> None:
        self._stacks.pop(window_id, None)

    def prune_stale(self, is_alive: Callable[[Hashable], bool]) -> int:
        dead = [k for k in self._stacks if not is_alive(k)]
        for k in dead:
            del self._stacks[k]
        return len(dead)

    def __len__(self) -> int:
        return sum(len(s) for s in self._stacks.values())
