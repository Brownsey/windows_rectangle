"""Tests for windows_rectangle.monitors_view — the --print-monitors formatter.

Pure: feeds in a list of MonitorInfo, checks the text/dict/JSON output.
No win32 imports.
"""

from __future__ import annotations

import json

from windows_rectangle.core.geometry import Rect
from windows_rectangle.monitors_view import (
    monitors_to_dicts,
    monitors_to_json,
    monitors_to_text,
)
from windows_rectangle.ports.window_manager import MonitorInfo


def _make(handle: int, x: int, y: int, w: int, h: int, *, taskbar: int = 40, primary: bool = False):
    bounds = Rect(x, y, w, h)
    work = Rect(x, y, w, max(1, h - taskbar))
    return MonitorInfo(handle=handle, bounds=bounds, work_area=work, is_primary=primary)


def test_dicts_preserve_geometry():
    monitors = [
        _make(1, 0, 0, 1920, 1080, primary=True),
        _make(2, 1920, 0, 2560, 1440),
    ]
    out = monitors_to_dicts(monitors)
    assert out[0]["is_primary"] is True
    assert out[0]["bounds"] == {"x": 0, "y": 0, "width": 1920, "height": 1080}
    assert out[0]["work_area"]["height"] == 1080 - 40
    assert out[1]["bounds"]["width"] == 2560


def test_dicts_expose_inferred_taskbar_height():
    """Surfacing the taskbar inference helps users debug why an action
    that uses work_area lands above where they expected."""
    monitors = [_make(1, 0, 0, 1920, 1080, taskbar=64)]
    out = monitors_to_dicts(monitors)
    assert out[0]["taskbar_height_inferred"] == 64


def test_text_marks_primary():
    monitors = [_make(1, 0, 0, 1920, 1080, primary=True), _make(2, 1920, 0, 1024, 768)]
    out = monitors_to_text(monitors)
    assert "(primary)" in out
    # Non-primary monitor doesn't get the marker.
    assert out.count("(primary)") == 1


def test_text_empty_list_is_helpful():
    assert monitors_to_text([]) == "No monitors detected."


def test_text_shows_taskbar_when_present():
    monitors = [_make(1, 0, 0, 1920, 1080, taskbar=40, primary=True)]
    out = monitors_to_text(monitors)
    assert "taskbar  : ~40px" in out


def test_text_skips_taskbar_line_when_zero():
    """If work_area == bounds (no taskbar reserved), the taskbar line
    is omitted — otherwise users see a misleading '~0px (inferred)'."""
    monitors = [_make(1, 0, 0, 1920, 1080, taskbar=0)]
    out = monitors_to_text(monitors)
    assert "taskbar" not in out


def test_json_round_trips():
    monitors = [_make(1, 0, 0, 1920, 1080, primary=True)]
    out = json.loads(monitors_to_json(monitors))
    assert isinstance(out, list)
    assert out[0]["bounds"]["width"] == 1920
    assert out[0]["is_primary"] is True
