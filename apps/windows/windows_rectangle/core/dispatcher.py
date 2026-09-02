"""Action dispatcher — port-agnostic engine that turns Action requests into
window moves, with cycling + undo + multi-monitor support.

Wires `actions`, `cycle`, `history`, `monitors` together against the
`WindowManager` port. Pure orchestration; no OS calls of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..ports.window_manager import WindowManager
from . import monitors as monitors_mod
from .actions import Action, apply, is_geometry_action
from .cycle import CycleState
from .eligibility import Capability, classify
from .geometry import Rect
from .history import History

_DISPLAY_ACTION_INDEX = {
    Action.DISPLAY_1: 0,
    Action.DISPLAY_2: 1,
    Action.DISPLAY_3: 2,
    Action.DISPLAY_4: 3,
    Action.DISPLAY_5: 4,
    Action.DISPLAY_6: 5,
    Action.DISPLAY_7: 6,
    Action.DISPLAY_8: 7,
    Action.DISPLAY_9: 8,
}


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """What happened when `dispatch` ran. Mostly for tests + observability."""

    action: Action
    handle: object | None
    before: Rect | None
    after: Rect | None
    moved: bool
    reason: str  # "ok", "no_active_window", "no_monitor", "blocked", "no_undo"


class Dispatcher:
    """Front door: `dispatch(action)` does the right thing for the active window."""

    def __init__(
        self,
        windows: WindowManager,
        *,
        gap: int = 0,
        cycle: CycleState | None = None,
        history: History | None = None,
        record_history: bool = True,
        almost_maximize_scale: float | None = None,
    ) -> None:
        self._windows = windows
        self._gap = gap
        self._cycle = cycle if cycle is not None else CycleState()
        self._history = history if history is not None else History()
        self._record = record_history
        # None → use the module-level default. Settings-driven callers
        # pass settings.almost_maximize_scale explicitly so the prefs
        # slider takes effect at runtime.
        self.almost_maximize_scale = almost_maximize_scale

    # ----- public API -----

    @property
    def gap(self) -> int:
        return self._gap

    @gap.setter
    def gap(self, value: int) -> None:
        self._gap = max(0, value)

    def dispatch(self, action: Action) -> DispatchResult:
        handle = self._windows.get_active_window()
        if handle is None:
            return DispatchResult(action, None, None, None, False, "no_active_window")

        if action == Action.RESTORE:
            return self._restore(handle)

        if action in (Action.NEXT_DISPLAY, Action.PREV_DISPLAY):
            return self._move_to_neighbor_display(handle, action)

        if action in _DISPLAY_ACTION_INDEX:
            return self._move_to_display(handle, action, _DISPLAY_ACTION_INDEX[action])

        if action == Action.TOGGLE_ALWAYS_ON_TOP:
            return self._toggle_always_on_top(handle)

        if is_geometry_action(action):
            return self._apply_geometry(handle, action)

        # Defensive: every defined Action is currently RESTORE,
        # NEXT/PREV_DISPLAY, or geometry, so this branch is unreachable
        # until someone adds a new Action without wiring it. The structured
        # result is safer than a KeyError.
        return DispatchResult(  # pragma: no cover
            action, handle, None, None, False, "unsupported"
        )

    # ----- internals -----

    def _apply_geometry(self, handle: object, action: Action) -> DispatchResult:
        monitor = self._windows.monitor_for_window(handle)
        if monitor is None:
            return DispatchResult(action, handle, None, None, False, "no_monitor")

        cap = classify(self._windows.get_window_flags(handle))
        if cap is Capability.NONE:
            return DispatchResult(action, handle, None, None, False, "ineligible")

        effective = self._cycle.next_action(handle, action)
        before = self._windows.get_window_rect(handle)
        target = apply(
            effective,
            before,
            monitor.work_area,
            self._gap,
            almost_maximize_scale=self.almost_maximize_scale,
        )

        if Capability.RESIZE not in cap:
            # Move-only window (e.g. fixed-size dialog) — keep its size,
            # center it at the target rect's center.
            target = Rect(
                target.center_x - before.width // 2,
                target.center_y - before.height // 2,
                before.width,
                before.height,
            ).clamp_to(monitor.work_area)

        return self._move(handle, action, before, target)

    def _move_to_neighbor_display(self, handle: object, action: Action) -> DispatchResult:
        all_monitors = self._windows.list_monitors()
        if len(all_monitors) <= 1:
            # Only one screen: nothing to do, but treat as success.
            return DispatchResult(action, handle, None, None, False, "single_monitor")

        current = self._windows.monitor_for_window(handle)
        if current is None:
            return DispatchResult(action, handle, None, None, False, "no_monitor")

        direction = 1 if action == Action.NEXT_DISPLAY else -1
        destination = monitors_mod.neighbor(all_monitors, current, direction=direction)
        before = self._windows.get_window_rect(handle)
        target = monitors_mod.move_to_monitor(before, current, destination)
        return self._move(handle, action, before, target)

    def _move_to_display(
        self, handle: object, action: Action, display_index: int
    ) -> DispatchResult:
        monitors = self._windows.list_monitors()
        if display_index >= len(monitors):
            return DispatchResult(action, handle, None, None, False, "display_unavailable")
        current = self._windows.monitor_for_window(handle)
        if current is None:
            return DispatchResult(action, handle, None, None, False, "no_monitor")
        before = self._windows.get_window_rect(handle)
        target = monitors_mod.move_to_monitor(before, current, monitors[display_index])
        return self._move(handle, action, before, target)

    def _restore(self, handle: object) -> DispatchResult:
        previous = self._history.pop(handle)
        if previous is None:
            return DispatchResult(Action.RESTORE, handle, None, None, False, "no_undo")
        before = self._windows.get_window_rect(handle)
        # Don't re-record the restore itself in history.
        ok = self._windows.set_window_rect(handle, previous)
        return DispatchResult(
            Action.RESTORE,
            handle,
            before,
            previous if ok else None,
            ok,
            "ok" if ok else "blocked",
        )

    def _toggle_always_on_top(self, handle: object) -> DispatchResult:
        before = self._windows.get_window_rect(handle)
        enabled = not self._windows.is_always_on_top(handle)
        ok = self._windows.set_always_on_top(handle, enabled)
        return DispatchResult(
            Action.TOGGLE_ALWAYS_ON_TOP,
            handle,
            before,
            before if ok else None,
            ok,
            "ok" if ok else "blocked",
        )

    def _move(self, handle: object, action: Action, before: Rect, target: Rect) -> DispatchResult:
        if target == before:
            return DispatchResult(action, handle, before, before, False, "no_change")
        # Brief §5 #4: SetWindowPos misbehaves on maximized/snapped windows.
        # Restore first; the dispatcher's `before` rect is still the pre-action
        # rect for the undo entry, so RESTORE re-maximizes via the recorded shape.
        if self._windows.is_maximized(handle):
            self._windows.restore_window(handle)
        if self._record:
            self._history.push(handle, before)
        ok = self._windows.set_window_rect(handle, target)
        if not ok:
            # Move was blocked (UIPI / elevated window) — drop the undo entry we just pushed.
            if self._record:
                self._history.pop(handle)
            return DispatchResult(action, handle, before, None, False, "blocked")
        return DispatchResult(action, handle, before, target, True, "ok")

    # ----- housekeeping (called by adapters periodically) -----

    def prune_stale_state(self, is_alive: Callable[[object], bool] | None = None) -> int:
        """Drop cycle/history entries for windows that no longer exist.

        If `is_alive` not supplied, falls back to the WindowManager port.
        Returns total entries dropped.

        Memoizes is_alive across the cycle + history sweeps so a HWND
        that appears in both data structures (the common case after the
        user has dispatched anything) only costs one IsWindow syscall.
        """
        raw = is_alive if is_alive is not None else self._windows.is_window_valid
        cache: dict[object, bool] = {}

        def check(wid: object) -> bool:
            if wid not in cache:
                cache[wid] = raw(wid)
            return cache[wid]

        return self._cycle.prune_stale(check) + self._history.prune_stale(check)
