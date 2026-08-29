[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $ScriptDir
}

$ResolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path.TrimEnd("\")

function Test-ContainsText {
    param(
        [AllowNull()][string]$Text,
        [string]$Needle
    )

    if (-not $Text) {
        return $false
    }
    return $Text.IndexOf($Needle, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Test-IsWindowsRectangleProcess {
    param($Process)

    $name = [string]$Process.Name
    $commandLine = [string]$Process.CommandLine
    $exePath = [string]$Process.ExecutablePath
    $inRepo = (Test-ContainsText $commandLine $ResolvedRepoRoot) -or
        (Test-ContainsText $exePath $ResolvedRepoRoot)

    if ($name -match "^(windows-rectangle|windows_rectangle|WindowsRectangle)(\.exe)?$") {
        return $true
    }

    if ($name -match "^pythonw?\.exe$") {
        if ($commandLine -match "(^|\s)-m\s+windows_rectangle(\s|$)") {
            return $true
        }
        if ($inRepo -and (Test-ContainsText $commandLine "windows_rectangle")) {
            return $true
        }
    }

    if ($inRepo -and (Test-ContainsText $commandLine "windows-rectangle")) {
        return $true
    }

    return $false
}

$currentProcessIds = [System.Collections.Generic.HashSet[int]]::new()
$null = $currentProcessIds.Add([int]$PID)

$current = Get-CimInstance Win32_Process -Filter "ProcessId = $PID" -ErrorAction SilentlyContinue
while ($null -ne $current -and $current.ParentProcessId) {
    $parentId = [int]$current.ParentProcessId
    if (-not $currentProcessIds.Add($parentId)) {
        break
    }
    $current = Get-CimInstance Win32_Process -Filter "ProcessId = $parentId" -ErrorAction SilentlyContinue
}

$targets = Get-CimInstance Win32_Process |
    Where-Object {
        -not $currentProcessIds.Contains([int]$_.ProcessId) -and
        (Test-IsWindowsRectangleProcess $_)
    }

$stopped = 0
$failed = 0

foreach ($target in $targets) {
    try {
        if (-not $Quiet) {
            Write-Host "Stopping existing Windows Rectangle process $($target.ProcessId)..."
        }
        Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
        $stopped += 1
    } catch {
        $failed += 1
        Write-Warning "Could not stop process $($target.ProcessId): $($_.Exception.Message)"
    }
}

if (-not $Quiet -and $stopped -eq 0 -and $failed -eq 0) {
    Write-Host "No existing Windows Rectangle instance found."
}

if ($failed -gt 0) {
    exit 1
}

exit 0
