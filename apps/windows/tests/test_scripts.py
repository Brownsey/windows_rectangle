"""Run the stop script with process discovery and termination isolated."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_packaged_smoke_waits_for_gui_process_and_rejects_nonzero_exit():
    source = (ROOT / "scripts/build-windows.ps1").read_text()
    helpers = source[
        source.index("function Invoke-Native") : source.index("function Test-CommandExists")
    ]
    # pythonw is a GUI-subsystem executable like the packaged app. The unknown
    # flag exits nonzero; PowerShell must wait and inspect this process's result.
    executable = str(Path(sys.executable).with_name("pythonw.exe")).replace("'", "''")
    command = f"""$ErrorActionPreference = 'Stop'
$global:LASTEXITCODE = 0
{helpers}
Test-PackagedExecutable '{executable}'
Write-Output 'incorrectly accepted failed smoke test'
exit 0
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert "incorrectly accepted" not in result.stdout


def test_stop_targets_app_entry_points_without_killing_test_or_build_processes():
    python = str(ROOT / ".venv/Scripts/python.exe")
    processes = [
        {
            "ProcessId": 501,
            "Name": "python.exe",
            "ExecutablePath": python,
            "CommandLine": f'"{python}" -m pytest apps/windows/tests',
        },
        {
            "ProcessId": 502,
            "Name": "python.exe",
            "ExecutablePath": python,
            "CommandLine": f'"{python}" -m PyInstaller windows_rectangle.spec',
        },
        {
            "ProcessId": 503,
            "Name": "python.exe",
            "ExecutablePath": python,
            "CommandLine": f'"{python}" -m windows_rectangle --tray',
        },
    ]
    payload = json.dumps(processes).replace("'", "''")
    script = str(ROOT / "scripts/stop-windows.ps1").replace("'", "''")
    command = f"""function Get-CimInstance {{
    param($ClassName, $Filter, $ErrorAction)
    if (-not $Filter) {{ foreach ($item in ('{payload}' | ConvertFrom-Json)) {{ $item }} }}
}}
function Stop-Process {{
    param($Id, [switch]$Force, $ErrorAction)
    Write-Output "STOP:$Id"
}}
& '{script}' -Quiet
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["STOP:503"]
