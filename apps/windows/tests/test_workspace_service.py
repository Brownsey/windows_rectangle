"""Tests for capture/apply workspace orchestration."""

from dataclasses import dataclass, field

from windows_rectangle.core.geometry import Rect
from windows_rectangle.core.workspace_service import (
    apply_workspace,
    capture_workspace,
    launch_and_apply_workspace,
)
from windows_rectangle.core.workspaces import (
    NormalizedRect,
    WindowIdentity,
    WindowMatcher,
    Workspace,
    WorkspacePlacement,
)


@dataclass
class WorkspaceManager:
    windows: list[WindowIdentity]
    rects: dict[object, Rect]
    work_areas: list[Rect]
    monitor_indexes: dict[object, int]
    maximized: set[object] = field(default_factory=set)
    blocked: set[object] = field(default_factory=set)
    moves: list[tuple[object, Rect]] = field(default_factory=list)
    launches: list[str] = field(default_factory=list)

    def list_windows(self):
        return list(self.windows)

    def list_work_areas(self):
        return list(self.work_areas)

    def get_window_rect(self, handle):
        return self.rects[handle]

    def monitor_index_for_window(self, handle):
        return self.monitor_indexes.get(handle)

    def is_maximized(self, handle):
        return handle in self.maximized

    def restore_window(self, handle):
        self.maximized.discard(handle)

    def set_window_rect(self, handle, rect):
        if handle in self.blocked:
            return False
        self.moves.append((handle, rect))
        self.rects[handle] = rect
        return True

    def launch(self, command):
        self.launches.append(command)
        self.windows.append(WindowIdentity(99, "Alice - RuneLite", "runelite.exe"))
        self.rects[99] = Rect(100, 100, 800, 600)
        self.monitor_indexes[99] = 0


def manager():
    return WorkspaceManager(
        windows=[
            WindowIdentity(1, "Slack", "slack.exe"),
            WindowIdentity(2, "Inbox - Outlook", "outlook.exe"),
            WindowIdentity(3, "Docs - Chrome", "chrome.exe"),
        ],
        rects={
            1: Rect(0, 0, 960, 540),
            2: Rect(0, 540, 960, 540),
            3: Rect(960, 0, 960, 1080),
        },
        work_areas=[Rect(0, 0, 1920, 1080)],
        monitor_indexes={1: 0, 2: 0, 3: 0},
    )


def test_capture_then_apply_restores_office_layout():
    wm = manager()
    workspace = capture_workspace(wm, "Office")
    wm.rects = {handle: Rect(20, 20, 500, 400) for handle in wm.rects}
    wm.maximized.add(3)
    result = apply_workspace(wm, workspace)
    assert result.moved == 3
    assert wm.rects[1] == Rect(0, 0, 960, 540)
    assert wm.rects[2] == Rect(0, 540, 960, 540)
    assert wm.rects[3] == Rect(960, 0, 960, 1080)
    assert 3 not in wm.maximized


def test_apply_reports_missing_and_blocked_windows():
    wm = manager()
    workspace = capture_workspace(wm, "Office")
    wm.windows = wm.windows[:2]
    wm.blocked.add(2)
    result = apply_workspace(wm, workspace)
    assert [item.status for item in result.placements] == ["moved", "blocked", "not_found"]
    assert "administrator" in result.placements[1].detail


def test_capture_skips_windows_without_a_monitor():
    wm = manager()
    wm.monitor_indexes.pop(2)
    workspace = capture_workspace(wm, "Office")
    assert [placement.name for placement in workspace.placements] == ["Slack", "Docs - Chrome"]


def test_capture_excludes_its_own_editor_window():
    wm = manager()
    wm.windows.append(WindowIdentity(9, "Windows Rectangle — Workspaces", "python.exe"))
    wm.rects[9] = Rect(100, 100, 900, 700)
    wm.monitor_indexes[9] = 0
    workspace = capture_workspace(wm, "Office")
    assert all("Windows Rectangle" not in placement.name for placement in workspace.placements)


def test_launch_and_apply_starts_missing_app_then_positions_it():
    wm = manager()
    wm.windows = []
    workspace = Workspace(
        "gaming",
        "RuneScape",
        (
            WorkspacePlacement(
                "alice",
                "Alice",
                WindowMatcher(process_name="runelite.exe", title_contains="Alice"),
                NormalizedRect(0, 0, 5000, 10000),
                launch_command=r"C:\RuneLite\RuneLite.exe --profile Alice",
            ),
        ),
    )

    result = launch_and_apply_workspace(wm, workspace, timeout=0)

    assert wm.launches == [r"C:\RuneLite\RuneLite.exe --profile Alice"]
    assert result.moved == 1
    assert wm.rects[99] == Rect(0, 0, 960, 1080)
