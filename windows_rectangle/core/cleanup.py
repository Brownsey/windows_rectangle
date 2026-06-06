"""Cleanup registry — graceful shutdown plumbing (brief §5 #11).

The mouse hook and global hotkeys, if not explicitly released, persist
past process exit and degrade the OS. We register every resource that
needs unwinding here, and the composition root invokes the registry
from every shutdown path: tray "Exit", WM_CLOSE, atexit, SIGTERM,
and finally an `__exit__`/`try-finally` around the main loop so a
crash still unwinds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterator


_log = logging.getLogger(__name__)

CleanupFn = Callable[[], None]


@dataclass(slots=True)
class CleanupRegistry:
    """LIFO cleanup stack. Tolerates per-handler exceptions.

    Behaviour:
    - `register(fn)` adds `fn` to the unwinding stack.
    - `run()` invokes every registered fn in reverse order. Idempotent —
      calling it twice is safe (second call is a no-op).
    - Exceptions in handlers are logged, not propagated, so a single
      broken handler can't strand the rest of the stack.
    """

    _stack: list[CleanupFn] = field(default_factory=list)
    _ran: bool = False

    def register(self, fn: CleanupFn) -> None:
        if self._ran:
            # Late-registered handlers run immediately so the caller
            # doesn't have to special-case shutdown ordering.
            self._safe_call(fn)
            return
        self._stack.append(fn)

    def __len__(self) -> int:
        return len(self._stack)

    def run(self) -> int:
        """Run all registered cleanups. Returns count run."""
        if self._ran:
            return 0
        self._ran = True
        count = 0
        # LIFO — last registered runs first.
        while self._stack:
            fn = self._stack.pop()
            self._safe_call(fn)
            count += 1
        return count

    def __enter__(self) -> "CleanupRegistry":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Always unwind, even on exception.
        self.run()

    @staticmethod
    def _safe_call(fn: CleanupFn) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 — by design
            _log.exception("cleanup handler raised; continuing")

    # Mostly for tests / introspection.
    def __iter__(self) -> Iterator[CleanupFn]:
        return iter(self._stack)
