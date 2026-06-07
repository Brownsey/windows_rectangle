"""Drag-to-edge session state (brief §2 #13).

Wires:
  - `throttle.LatestValue` for the fast mouse-hook write path,
  - `throttle.Throttle` to rate-limit the snap-zone computation,
  - `snap.find_snap` for the actual classification.

Usage (from adapters):
    session = DragSession(monitors=wm.list_monitors(), gap=settings.gap)
    session.start(window_rect)
    # mouse hook thread (fast):
    session.update(x, y)
    # UI timer thread (~60 Hz):
    hit = session.poll()
    if hit and hit.action: overlay.show(hit.target)
    # on mouse-up:
    final = session.finish()
    if final and final.action: dispatcher.dispatch(final.action)
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..ports.window_manager import MonitorInfo
from .geometry import Rect
from .snap import SnapHit, SnapZone, find_snap
from .throttle import LatestValue, Throttle

# 16ms ≈ 60 Hz — matches typical Win32 mouse-move event cadence and Qt
# repaint rate. Anything faster is wasted compute.
DEFAULT_POLL_INTERVAL = 1.0 / 60


@dataclass(slots=True)
class DragSession:
    """Stateful coordinator for a single drag-and-snap interaction.

    Thread model:
        - `update(x, y)` is hot-path; safe from the mouse hook thread.
        - `poll()` and `finish()` are main-thread only.
    """

    monitors: Sequence[MonitorInfo]
    gap: int = 0
    poll_interval: float = DEFAULT_POLL_INTERVAL
    _coords: LatestValue[tuple[int, int]] = field(init=False)
    _throttle: Throttle = field(init=False)
    _last_hit: SnapHit | None = field(default=None, init=False)
    _window: Rect | None = field(default=None, init=False)
    _active: bool = field(default=False, init=False)
    _clock: Callable[[], float] = field(default=time.monotonic)

    def __post_init__(self) -> None:
        self._coords = LatestValue()
        self._throttle = Throttle(interval=self.poll_interval, _clock=self._clock)

    # ----- lifecycle --------------------------------------------------

    def start(self, window: Rect) -> None:
        """Begin a session tracking a drag of `window`."""
        self._active = True
        self._window = window
        self._last_hit = None
        self._coords = LatestValue()
        self._throttle.reset()

    @property
    def active(self) -> bool:
        return self._active

    # ----- producer (mouse hook) --------------------------------------

    def update(self, x: int, y: int) -> None:
        """Mouse moved. O(1), non-blocking, safe from hook thread."""
        if not self._active:
            return
        self._coords.set((x, y))

    # ----- consumer (UI timer) ----------------------------------------

    def poll(self) -> SnapHit | None:
        """Drain the latest cursor pos and compute the snap hit if throttle allows.

        Returns the new SnapHit if a fresh computation happened, the cached
        previous hit if throttle rejected the call, or None if no coords
        have arrived yet.
        """
        if not self._active:
            return None
        if not self._throttle.should_run():
            return self._last_hit
        coords = self._coords.pop()
        if coords is None:
            return self._last_hit
        x, y = coords
        hit = find_snap(x, y, self.monitors, window=self._window, gap=self.gap)
        self._last_hit = hit if hit.zone is not SnapZone.NONE else None
        return self._last_hit

    # ----- finish -----------------------------------------------------

    def finish(self) -> SnapHit | None:
        """End the session. Returns the last snap hit (if any) for the
        dispatcher to apply. Resets state regardless.
        """
        result = self._last_hit
        self._active = False
        self._last_hit = None
        self._window = None
        self._coords = LatestValue()
        return result

    def cancel(self) -> None:
        """Abort the session without returning a hit. Used on Escape press."""
        self.finish()
