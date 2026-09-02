"""Capture and apply named workspaces through a narrow OS-facing protocol."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .geometry import Rect
from .workspaces import (
    NormalizedRect,
    WindowIdentity,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
    new_id,
    plan_workspace,
)


class WorkspaceWindows(Protocol):
    def list_windows(self) -> list[WindowIdentity]: ...
    def list_work_areas(self) -> list[Rect]: ...
    def get_window_rect(self, handle: object) -> Rect: ...
    def monitor_index_for_window(self, handle: object) -> int | None: ...
    def is_maximized(self, handle: object) -> bool: ...
    def restore_window(self, handle: object) -> None: ...
    def set_window_rect(self, handle: object, rect: Rect) -> bool: ...
    def launch(self, command: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PlacementResult:
    placement_id: str
    status: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceResult:
    placements: tuple[PlacementResult, ...]

    @property
    def moved(self) -> int:
        return sum(item.status == "moved" for item in self.placements)


def capture_workspace(manager: WorkspaceWindows, name: str) -> Workspace:
    """Capture eligible visible windows using strong editable default rules."""
    if not name.strip():
        raise ValueError("workspace name cannot be empty")
    work_areas = manager.list_work_areas()
    placements: list[WorkspacePlacement] = []
    for window in manager.list_windows():
        # Never save this utility's own preferences/editor windows into a
        # workspace captured while its UI is open.
        if window.title.casefold().startswith("windows rectangle"):
            continue
        monitor_index = manager.monitor_index_for_window(window.handle)
        if monitor_index is None or monitor_index >= len(work_areas):
            continue
        try:
            rect = NormalizedRect.from_rect(
                manager.get_window_rect(window.handle), work_areas[monitor_index]
            )
            matcher = WindowMatcher(
                process_name=window.process_name,
                title_contains=window.title,
            )
        except ValueError:
            continue
        placements.append(
            WorkspacePlacement(
                id=new_id(),
                name=window.title,
                matcher=matcher,
                rect=rect,
                monitor_index=monitor_index,
            )
        )
    return Workspace(id=new_id(), name=name.strip(), placements=tuple(placements))


def apply_workspace(manager: WorkspaceWindows, workspace: Workspace) -> WorkspaceResult:
    """Plan and apply a workspace, returning a user-displayable result per entry."""
    plan = plan_workspace(workspace, manager.list_windows(), manager.list_work_areas())
    results: list[PlacementResult] = []
    moves = {move.placement_id: move for move in plan.moves}
    for placement in workspace.placements:
        move = moves.get(placement.id)
        if move is None:
            results.append(PlacementResult(placement.id, "not_found", "No matching window"))
            continue
        try:
            if manager.is_maximized(move.handle):
                manager.restore_window(move.handle)
            ok = manager.set_window_rect(move.handle, move.rect)
        except OSError as exc:
            results.append(PlacementResult(placement.id, "blocked", str(exc)))
        else:
            status = "moved" if ok else "blocked"
            detail = "" if ok else "Windows refused the move; administrator access may be needed"
            results.append(PlacementResult(placement.id, status, detail))
    return WorkspaceResult(tuple(results))


def launch_and_apply_workspace(
    manager: WorkspaceWindows,
    workspace: Workspace,
    *,
    timeout: float = 12.0,
    poll_interval: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> WorkspaceResult:
    """Launch missing configured apps, wait for their windows, then arrange all matches."""
    initial = plan_workspace(workspace, manager.list_windows(), manager.list_work_areas())
    matched = {move.placement_id for move in initial.moves}
    launcher = getattr(manager, "launch", None)
    launched: set[str] = set()
    launch_errors: dict[str, str] = {}
    for placement in workspace.placements:
        command = placement.launch_command.strip()
        if placement.id in matched or not command:
            continue
        if launcher is None:
            launch_errors[placement.id] = "This window manager cannot launch applications"
            continue
        try:
            launcher(command)
            launched.add(placement.id)
        except OSError as exc:
            launch_errors[placement.id] = str(exc)

    if launched and timeout > 0:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            current = plan_workspace(workspace, manager.list_windows(), manager.list_work_areas())
            current_matches = {move.placement_id for move in current.moves}
            if launched <= current_matches:
                break
            sleep(min(poll_interval, max(0.0, deadline - monotonic())))

    applied = apply_workspace(manager, workspace)
    results: list[PlacementResult] = []
    for result in applied.placements:
        if result.placement_id in launch_errors:
            results.append(
                PlacementResult(
                    result.placement_id, "launch_failed", launch_errors[result.placement_id]
                )
            )
        elif result.placement_id in launched and result.status == "not_found":
            results.append(
                PlacementResult(
                    result.placement_id,
                    "not_found",
                    "Application launched but no matching window appeared within "
                    f"{timeout:g} seconds",
                )
            )
        else:
            results.append(result)
    return WorkspaceResult(tuple(results))
