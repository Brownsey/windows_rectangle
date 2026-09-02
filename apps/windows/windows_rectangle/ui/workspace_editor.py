"""Staged editing and validation for named multi-window workspaces."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace

from ..core.keymap import UnsupportedKeyError, translate
from ..core.shortcuts import (
    ShortcutParseError,
    is_reserved,
    normalise,
    parse,
)
from ..core.workspace_presets import preset_rect
from ..core.workspace_service import WorkspaceWindows, capture_workspace
from ..core.workspace_templates import office_workspace, runescape_workspace
from ..core.workspaces import (
    NormalizedRect,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
    match_workspace_windows,
    new_id,
    plan_workspace,
)
from ..ports.config_store import Settings


@dataclass(frozen=True, slots=True)
class WorkspaceValidation:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class PositionRecordResult:
    updated: int
    not_found: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceSaveOutcome:
    saved: bool
    validation: WorkspaceValidation
    error: str = ""


class WorkspaceEditorController:
    def __init__(self, settings: Settings) -> None:
        self.baseline = deepcopy(settings)
        self.staged = deepcopy(settings)

    @property
    def is_dirty(self) -> bool:
        return self.staged != self.baseline

    def get(self, workspace_id: str) -> Workspace:
        try:
            return next(item for item in self.staged.workspaces if item.id == workspace_id)
        except StopIteration as exc:
            raise KeyError(workspace_id) from exc

    def rebase_onto(self, current: Settings) -> None:
        """Keep layout edits while adopting newer shortcut/general settings."""
        merged = deepcopy(current)
        baseline_by_id = {workspace.id: workspace for workspace in self.baseline.workspaces}
        staged_by_id = {workspace.id: workspace for workspace in self.staged.workspaces}
        current_by_id = {workspace.id: workspace for workspace in current.workspaces}
        workspaces: list[Workspace] = []
        for staged in self.staged.workspaces:
            baseline = baseline_by_id.get(staged.id)
            if baseline is None or staged != baseline:
                workspaces.append(deepcopy(staged))
            else:
                workspaces.append(deepcopy(current_by_id.get(staged.id, staged)))
        for workspace in current.workspaces:
            if workspace.id not in baseline_by_id and workspace.id not in staged_by_id:
                workspaces.append(deepcopy(workspace))
        merged.workspaces = tuple(workspaces)
        if self.staged.active_workspace_id != self.baseline.active_workspace_id:
            merged.active_workspace_id = self.staged.active_workspace_id
        self.staged = merged

    def capture(self, manager: WorkspaceWindows, name: str) -> Workspace:
        workspace = capture_workspace(manager, name)
        self.staged.workspaces = (*self.staged.workspaces, workspace)
        self.staged.active_workspace_id = workspace.id
        return workspace

    def create(self, name: str) -> Workspace:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("workspace name cannot be empty")
        workspace = Workspace(new_id(), clean_name, ())
        self.staged.workspaces = (*self.staged.workspaces, workspace)
        self.staged.active_workspace_id = workspace.id
        return workspace

    def add_office_template(self, name: str = "Office focus") -> Workspace:
        workspace = office_workspace(name)
        self.staged.workspaces = (*self.staged.workspaces, workspace)
        self.staged.active_workspace_id = workspace.id
        return workspace

    def add_runescape_template(
        self, accounts: list[str], name: str = "RuneScape accounts"
    ) -> Workspace:
        workspace = runescape_workspace(accounts, name)
        self.staged.workspaces = (*self.staged.workspaces, workspace)
        self.staged.active_workspace_id = workspace.id
        return workspace

    def duplicate(self, workspace_id: str) -> Workspace:
        source = self.get(workspace_id)
        duplicate = Workspace(
            new_id(),
            f"{source.name} copy",
            tuple(replace(placement, id=new_id()) for placement in source.placements),
        )
        self.staged.workspaces = (*self.staged.workspaces, duplicate)
        self.staged.active_workspace_id = duplicate.id
        return duplicate

    def add_placement(
        self,
        workspace_id: str,
        *,
        name: str,
        process_name: str = "",
        title_contains: str = "",
        title_regex: str = "",
        monitor_index: int = 0,
        preset_id: str = "full",
        launch_command: str = "",
    ) -> WorkspacePlacement:
        workspace = self.get(workspace_id)
        placement = WorkspacePlacement(
            new_id(),
            name.strip(),
            WindowMatcher(process_name.strip(), title_contains.strip(), title_regex.strip()),
            preset_rect(preset_id),
            monitor_index,
            launch_command.strip(),
        )
        self._replace_workspace(workspace_id, placements=(*workspace.placements, placement))
        return placement

    def set_placement_rect(
        self, workspace_id: str, placement_id: str, rect: NormalizedRect
    ) -> None:
        workspace = self.get(workspace_id)
        placements = tuple(
            replace(placement, rect=rect) if placement.id == placement_id else placement
            for placement in workspace.placements
        )
        if placements == workspace.placements:
            raise KeyError(placement_id)
        self._replace_workspace(workspace_id, placements=placements)

    def set_placement_preset(self, workspace_id: str, placement_id: str, preset_id: str) -> None:
        self.set_placement_rect(workspace_id, placement_id, preset_rect(preset_id))

    def rename(self, workspace_id: str, name: str) -> None:
        if not name.strip():
            raise ValueError("workspace name cannot be empty")
        self._replace_workspace(workspace_id, name=name.strip())

    def set_shortcut(self, workspace_id: str, shortcut: str) -> None:
        canonical = normalise(shortcut) if shortcut.strip() else ""
        self._replace_workspace(workspace_id, shortcut=canonical)

    def update_placement(
        self,
        workspace_id: str,
        placement_id: str,
        *,
        name: str,
        process_name: str,
        title_contains: str,
        title_regex: str,
        monitor_index: int,
        launch_command: str | None = None,
    ) -> None:
        workspace = self.get(workspace_id)
        matcher = WindowMatcher(
            process_name=process_name.strip(),
            title_contains=title_contains.strip(),
            title_regex=title_regex.strip(),
        )
        if not any(placement.id == placement_id for placement in workspace.placements):
            raise KeyError(placement_id)
        placements = tuple(
            replace(
                placement,
                name=name.strip(),
                matcher=matcher,
                monitor_index=monitor_index,
                launch_command=(
                    placement.launch_command if launch_command is None else launch_command.strip()
                ),
            )
            if placement.id == placement_id
            else placement
            for placement in workspace.placements
        )
        self._replace_workspace(workspace_id, placements=placements)

    def delete_workspace(self, workspace_id: str) -> None:
        remaining = tuple(item for item in self.staged.workspaces if item.id != workspace_id)
        if len(remaining) == len(self.staged.workspaces):
            raise KeyError(workspace_id)
        self.staged.workspaces = remaining
        if self.staged.active_workspace_id == workspace_id:
            self.staged.active_workspace_id = remaining[0].id if remaining else ""

    def delete_placement(self, workspace_id: str, placement_id: str) -> None:
        workspace = self.get(workspace_id)
        placements = tuple(item for item in workspace.placements if item.id != placement_id)
        if len(placements) == len(workspace.placements):
            raise KeyError(placement_id)
        self._replace_workspace(workspace_id, placements=placements)

    def match_counts(self, manager: WorkspaceWindows, workspace_id: str) -> tuple[int, int]:
        workspace = self.get(workspace_id)
        plan = plan_workspace(workspace, manager.list_windows(), manager.list_work_areas())
        return len(plan.moves), len(plan.unmatched_placements)

    def match_results(self, manager: WorkspaceWindows, workspace_id: str) -> dict[str, bool]:
        workspace = self.get(workspace_id)
        plan = plan_workspace(workspace, manager.list_windows(), manager.list_work_areas())
        matched = {move.placement_id for move in plan.moves}
        return {placement.id: placement.id in matched for placement in workspace.placements}

    def record_current_positions(
        self, manager: WorkspaceWindows, workspace_id: str
    ) -> PositionRecordResult:
        workspace = self.get(workspace_id)
        matches = match_workspace_windows(workspace.placements, manager.list_windows())
        handles = {match.placement_id: match.handle for match in matches.matches}
        work_areas = manager.list_work_areas()
        updated = 0
        placements: list[WorkspacePlacement] = []
        not_found = list(matches.unmatched_placements)
        for placement in workspace.placements:
            handle = handles.get(placement.id)
            if handle is None:
                placements.append(placement)
                continue
            monitor_index = manager.monitor_index_for_window(handle)
            if monitor_index is None or monitor_index >= len(work_areas):
                not_found.append(placement.id)
                placements.append(placement)
                continue
            try:
                rect = NormalizedRect.from_rect(
                    manager.get_window_rect(handle), work_areas[monitor_index]
                )
            except ValueError:
                not_found.append(placement.id)
                placements.append(placement)
                continue
            placements.append(replace(placement, rect=rect, monitor_index=monitor_index))
            updated += 1
        self._replace_workspace(workspace_id, placements=tuple(placements))
        return PositionRecordResult(updated, tuple(not_found))

    def validate(self) -> WorkspaceValidation:
        errors: list[str] = []
        warnings: list[str] = []
        shortcut_owners = {
            normalise(combo): action.value
            for action, combo in self.staged.shortcuts.items()
            if combo.strip()
        }
        names: set[str] = set()
        for workspace in self.staged.workspaces:
            folded_name = workspace.name.casefold()
            if folded_name in names:
                errors.append(f"Duplicate workspace name: {workspace.name}")
            names.add(folded_name)
            if workspace.shortcut:
                try:
                    combo = normalise(workspace.shortcut)
                except ShortcutParseError as exc:
                    errors.append(f"{workspace.name}: invalid shortcut ({exc})")
                else:
                    try:
                        translate(parse(combo))
                    except (ShortcutParseError, UnsupportedKeyError) as exc:
                        errors.append(f"{workspace.name}: unsupported shortcut ({exc})")
                        continue
                    owner = shortcut_owners.get(combo)
                    if owner is not None:
                        errors.append(f"{workspace.name}: shortcut already used by {owner}")
                    shortcut_owners[combo] = workspace.name
                    if is_reserved(combo):
                        warnings.append(f"{workspace.name}: shortcut is reserved by Windows")
            seen_rules: set[tuple[str, str, str]] = set()
            for placement in workspace.placements:
                matcher = placement.matcher
                rule = (
                    matcher.process_name.casefold(),
                    matcher.title_contains.casefold(),
                    matcher.title_regex,
                )
                if rule in seen_rules:
                    warnings.append(
                        f"{workspace.name}: {placement.name} has an ambiguous duplicate match rule"
                    )
                seen_rules.add(rule)
                if matcher.process_name and not (matcher.title_contains or matcher.title_regex):
                    warnings.append(
                        f"{workspace.name}: {placement.name} may match any window from that app"
                    )
        return WorkspaceValidation(tuple(errors), tuple(warnings))

    def commit(self, on_save=None, on_apply=None) -> WorkspaceValidation:
        report = self.validate()
        if not report.ok:
            return report
        if on_save is not None:
            on_save(self.staged)
        if on_apply is not None:
            on_apply(self.staged)
        self.baseline = deepcopy(self.staged)
        self.staged = deepcopy(self.baseline)
        return report

    def autosave(self, on_save=None, on_apply=None) -> WorkspaceSaveOutcome:
        """Persist a valid staged snapshot while retaining dirty state on failure."""
        report = self.validate()
        if not report.ok:
            return WorkspaceSaveOutcome(False, report)
        try:
            if on_save is not None:
                on_save(self.staged)
            if on_apply is not None:
                on_apply(self.staged)
        except Exception as exc:  # noqa: BLE001 - adapters surface errors in the UI
            return WorkspaceSaveOutcome(False, report, str(exc))
        self.baseline = deepcopy(self.staged)
        self.staged = deepcopy(self.baseline)
        return WorkspaceSaveOutcome(True, report)

    def _replace_workspace(self, workspace_id: str, **changes) -> None:
        found = False
        workspaces: list[Workspace] = []
        for workspace in self.staged.workspaces:
            if workspace.id == workspace_id:
                workspace = replace(workspace, **changes)
                found = True
            workspaces.append(workspace)
        if not found:
            raise KeyError(workspace_id)
        self.staged.workspaces = tuple(workspaces)
