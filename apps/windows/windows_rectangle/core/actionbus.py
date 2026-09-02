"""Thread-safe action marshalling (brief §5 #6 and #8).

Hotkey + mouse-hook callbacks run on their own daemon threads with
private Win32 message loops. They must return fast, so they don't
dispatch directly — they `submit` an Action onto this bus. The Qt
main thread drains the bus and calls the Dispatcher.

`queue.SimpleQueue` is unbounded and lock-free for single-producer-
single-consumer; we use it via `Queue` with optional size cap and
oldest-dropping overflow handling for safety.
"""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from dataclasses import dataclass, field

from .actions import Action

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class ActionBus:
    """A bounded action queue. Producer-safe across threads.

    `maxsize=0` means unbounded. When bounded and full, the oldest
    pending action is dropped (with a log warning) so the queue can't
    pile up forever during e.g. a UI hang.
    """

    maxsize: int = 256
    _q: queue.Queue[Action] = field(init=False)

    def __post_init__(self) -> None:
        self._q = queue.Queue(maxsize=self.maxsize)

    # ----- producer side (any thread) ---------------------------------

    def submit(self, action: Action) -> bool:
        """Enqueue an action. Returns False if the queue overflowed.

        Never blocks — hotkey threads cannot afford to block.
        """
        try:
            self._q.put_nowait(action)
            return True
        except queue.Full:
            # Drop one (the oldest) and retry once. Logs a warning so the
            # composition root can surface persistent overflow in the UI.
            try:
                dropped = self._q.get_nowait()
                _log.warning("ActionBus full; dropped %s", dropped.value)
                self._q.put_nowait(action)
            except queue.Empty:  # pragma: no cover — race; queue was drained
                pass
            return False

    # ----- consumer side (main / dispatcher thread) -------------------

    def drain(self, handler: Callable[[Action], None]) -> int:
        """Call `handler(action)` for every pending action. Returns count drained.

        Non-blocking. Safe to call repeatedly from the Qt event loop.
        """
        count = 0
        while True:
            try:
                action = self._q.get_nowait()
            except queue.Empty:
                return count
            try:
                handler(action)
            except Exception:  # noqa: BLE001 — by design; one bad action shouldn't kill the loop
                _log.exception("handler raised on %s; continuing", action.value)
            count += 1

    def pending(self) -> int:
        """Approximate number of queued actions (best-effort, not synchronised)."""
        return self._q.qsize()
