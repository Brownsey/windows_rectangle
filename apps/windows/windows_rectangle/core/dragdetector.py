"""Drag-detection state machine (brief §2 #13, §5 #7).

Translates a stream of raw mouse events from `Win32MouseHook` into
the higher-level begin/update/end protocol that `AppContext` exposes
for drag-to-edge snapping.

Why a separate class instead of inlining the logic in the adapter:
  - Pure-Python, no win32 imports → fully testable.
  - Lets the adapter stay a thin pump-and-dispatch wrapper.
  - Encodes the "click vs. drag" distinction in one place (a small
    movement threshold after LBUTTON_DOWN before we consider the user
    to be dragging — a 2-pixel jitter on a click must not trigger a
    snap session).

Lifecycle:
    LBUTTON_DOWN      → ARMED   (remember anchor (x, y))
    MOVE while ARMED  → if distance > threshold:  DRAGGING (callbacks.begin)
                        else: stay ARMED
    MOVE while DRAGGING → callbacks.update(x, y)
    LBUTTON_UP        → if DRAGGING: callbacks.end()
                        reset to IDLE

The detector itself does *not* call the OS; the callbacks supplied by
the adapter own that (they look up the active window for begin, etc.).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

# Squared-distance threshold. 5 pixels² ≈ a click-and-release-with-jitter
# noise floor on a 1080p display. Tuned conservatively — Rectangle uses a
# similar cushion on macOS.
DEFAULT_DRAG_THRESHOLD_PX = 5


class _State(StrEnum):
    IDLE = "idle"
    ARMED = "armed"
    DRAGGING = "dragging"


# Callback signatures the adapter must supply.
BeginCallback = Callable[[int, int], bool]  # (x, y) → True if a session started
UpdateCallback = Callable[[int, int], None]
EndCallback = Callable[[], None]


@dataclass(slots=True)
class DragDetector:
    """Pure state machine — feed it raw events, it calls your callbacks.

    The `on_begin` callback returns a bool: True if the caller actually
    started a session (e.g. the foreground window is eligible), False if
    not (in which case the detector returns to IDLE without arming an
    end-of-drag dispatch).
    """

    on_begin: BeginCallback
    on_update: UpdateCallback
    on_end: EndCallback
    threshold_px: int = DEFAULT_DRAG_THRESHOLD_PX
    _state: _State = field(default=_State.IDLE, init=False)
    _anchor: tuple[int, int] | None = field(default=None, init=False)

    # ----- raw-event sinks ------------------------------------------------

    def on_button_down(self, x: int, y: int) -> None:
        # Reentrant down events (e.g. a duplicate WH_MOUSE_LL deliver) just
        # re-anchor — never trigger a spurious begin.
        self._state = _State.ARMED
        self._anchor = (x, y)

    def on_move(self, x: int, y: int) -> None:
        if self._state is _State.IDLE:
            return
        if self._state is _State.ARMED:
            ax, ay = self._anchor or (x, y)
            dx, dy = x - ax, y - ay
            if dx * dx + dy * dy < self.threshold_px * self.threshold_px:
                return
            # Cross the threshold → ask the adapter whether the foreground
            # window is eligible. If not, fall back to IDLE so we don't
            # mis-route a stray LBUTTON_UP later.
            if not self.on_begin(x, y):
                self._state = _State.IDLE
                self._anchor = None
                return
            self._state = _State.DRAGGING
        # DRAGGING → fall through to update
        self.on_update(x, y)

    def on_button_up(self, x: int, y: int) -> None:
        was_dragging = self._state is _State.DRAGGING
        self._state = _State.IDLE
        self._anchor = None
        if was_dragging:
            self.on_end()

    # ----- introspection (for tests / debugging) --------------------------

    @property
    def state(self) -> str:
        return self._state.value

    def reset(self) -> None:
        """Force back to IDLE without firing on_end. Used on shutdown."""
        self._state = _State.IDLE
        self._anchor = None
