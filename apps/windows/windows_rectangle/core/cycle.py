"""Repeat-key cycling.

When the user presses the same shortcut twice within an idle window,
Rectangle cycles through related variants. E.g. repeated `LEFT_HALF` goes
left-half → left-third → left-two-thirds → left-half.

State is keyed by `(window_id, group)` so each window cycles independently.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field

from .actions import Action

# Cycle groups: pressing any action in the list advances to the next member.
CYCLE_GROUPS: list[tuple[Action, ...]] = [
    (Action.LEFT_HALF, Action.FIRST_THIRD, Action.FIRST_TWO_THIRDS),
    (Action.RIGHT_HALF, Action.LAST_THIRD, Action.LAST_TWO_THIRDS),
    (Action.TOP_HALF,),  # vertical halves don't cycle in Rectangle defaults
    (Action.BOTTOM_HALF,),
    (Action.CENTER_THIRD,),
]


def _group_for(action: Action) -> tuple[Action, ...] | None:
    for group in CYCLE_GROUPS:
        if action in group:
            return group
    return None


@dataclass(slots=True)
class _Entry:
    group: tuple[Action, ...]
    index: int
    last_press: float


@dataclass(slots=True)
class CycleState:
    """Per-window cycle tracker.

    `window_id` is typically an HWND (int) but the type is loose so tests
    can use strings.
    """

    idle_timeout: float = 1.5  # seconds; brief §5.9 "short idle timeout"
    _entries: dict[tuple[Hashable, tuple[Action, ...]], _Entry] = field(default_factory=dict)
    _clock: Callable[[], float] = field(default=time.monotonic)

    def next_action(self, window_id: Hashable, requested: Action) -> Action:
        """Return the action to actually execute for this key-press.

        - First press of a key (or after idle timeout) → `requested` itself.
        - Repeat press within timeout → next member of the cycle group.
        """
        group = _group_for(requested)
        if group is None or len(group) <= 1:
            return requested

        now = self._clock()
        key = (window_id, group)
        entry = self._entries.get(key)

        if entry is None or (now - entry.last_press) > self.idle_timeout:
            # First press → land on the action the user actually pressed.
            new_index = group.index(requested)
        else:
            new_index = (entry.index + 1) % len(group)

        self._entries[key] = _Entry(group=group, index=new_index, last_press=now)
        return group[new_index]

    def evict(self, window_id: Hashable) -> None:
        """Drop all cycle state for the given window (used when HWND closes)."""
        self._entries = {k: v for k, v in self._entries.items() if k[0] != window_id}

    def prune_stale(self, is_alive: Callable[[Hashable], bool]) -> int:
        """Drop entries whose window_id no longer passes `is_alive(id)`. Returns count dropped."""
        dead = {k for k in self._entries if not is_alive(k[0])}
        for k in dead:
            del self._entries[k]
        return len(dead)
