"""Thread-safe action marshalling (brief §5 #6 and #8).

Hotkey callbacks submit actions from their message-loop thread. The Qt
main thread drains bounded batches and calls the Dispatcher. Mouse input
uses a separate latest-state handoff so cursor motion cannot fill this queue.

`queue.Queue` provides synchronized storage with an optional size cap and
oldest-dropping overflow handling.
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
            except (queue.Empty, queue.Full):  # another producer/consumer won the race
                pass
            return False

    # ----- consumer side (main / dispatcher thread) -------------------

    def drain(self, handler: Callable[[Action], object], *, limit: int | None = None) -> int:
        """Handle the current batch, capped by `limit`. Returns count drained.

        Non-blocking. Safe to call repeatedly from the Qt event loop.
        """
        count = 0
        # A producer may refill during dispatch. Yield back to Qt after the
        # current batch instead of chasing a moving queue indefinitely.
        batch = self._q.qsize()
        if limit is not None:
            batch = min(batch, max(0, limit))
        for _ in range(batch):
            try:
                action = self._q.get_nowait()
            except queue.Empty:
                return count
            try:
                handler(action)
            except Exception:  # noqa: BLE001 — by design; one bad action shouldn't kill the loop
                _log.exception("handler raised on %s; continuing", action.value)
            count += 1
        return count

    def pending(self) -> int:
        """Approximate number of queued actions (best-effort, not synchronised)."""
        return self._q.qsize()
