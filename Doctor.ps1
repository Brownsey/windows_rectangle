<#
.SYNOPSIS
    Collect a one-shot "support package" for Windows Rectangle bug reports.

.DESCRIPTION
    Runs the bundled diagnostic flags against either the source tree or a
    built dist\WindowsRectangle.exe and writes the combined output to a
    plain-text file. Paste / attach that file when reporting an issue.

    The collected sections are:
      1. `WindowsRectangle --check-install`     install + dep importability
      2. `WindowsRectangle --print-monitors`    monitor geometry
      3. `WindowsRectangle --list-shortcuts`    current shortcut bindings
      4. Last 50 lines of `windows_rectangle.log` (if present)
      5. Build environment (Python version, OS build)

    Nothing personally identifying beyond the paths above is collected —
    the script does NOT touch the user's documents, browser data, etc.

.PARAMETER Exe
    Path to a WindowsRectangle executable. If unset the script prefers
    `dist\WindowsRectangle.exe` next to this script, falling back to
    `python -m windows_rectangle` against the source tree.

.PARAMETER OutputFile
    Where to write the support package. Defaults to
    "$env:TEMP\windows_rectangle_doctor.txt".

.PARAMETER Show
    Open the resulting file in the default text editor when done.

.EXAMPLE
    .\Doctor.ps1
    Run with defaults, print the file path at the end.

.EXAMPLE
    .\Doctor.ps1 -Show
    Open the report in Notepad after collecting.
#>

[CmdletBinding()]
param(
    [string] $Exe,
    [string] $OutputFile = (Join-Path $env:TEMP "windows_rectangle_doctor.txt"),
    [switch] $Show
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

function Section($title) {
    # Return ONE string with explicit newlines — PowerShell joins
    # array elements with spaces when you stringify them, which would
    # collapse "===\n title \n===" into a single line in the report.
    $nl = [Environment]::NewLine
    return "===================================================================="`
        + $nl + " $title"`
        + $nl + "===================================================================="`
        + $nl
}

function Resolve-Runner {
    if ($script:Exe) { return @{ Kind = "exe"; Cmd = $script:Exe } }
    $distExe = Join-Path $here "dist\WindowsRectangle.exe"
    if (Test-Path $distExe) {
        return @{ Kind = "exe"; Cmd = $distExe }
    }
    return @{ Kind = "python"; Cmd = "python -m windows_rectangle" }
}

$runner = Resolve-Runner

# Build the support package in memory then commit to disk at the end so
# a partial collection (e.g. python missing) leaves no half-written file.
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("Windows Rectangle - Doctor report")
[void]$sb.AppendLine("Generated: $(Get-Date -Format 'u')")
[void]$sb.AppendLine("Runner:    $($runner.Cmd) ($($runner.Kind))")
[void]$sb.AppendLine()

function Capture($title, $argstr) {
    [void]$sb.AppendLine((Section $title))
    try {
        if ($runner.Kind -eq "exe") {
            $output = & $runner.Cmd $argstr.Split(" ") 2>&1
        } else {
            $output = & python -m windows_rectangle $argstr.Split(" ") 2>&1
        }
        $rc = $LASTEXITCODE
        [void]$sb.AppendLine(($output -join [Environment]::NewLine))
        if ($rc -ne 0) {
            [void]$sb.AppendLine("(exit code $rc)")
        }
    } catch {
        [void]$sb.AppendLine("FAILED: $($_.Exception.Message)")
    }
    [void]$sb.AppendLine()
}

Capture "--check-install"   "--check-install"
Capture "--print-monitors"  "--print-monitors"
Capture "--list-shortcuts"  "--list-shortcuts"

# Last 50 lines of the log file, if it exists.
[void]$sb.AppendLine((Section "windows_rectangle.log (last 50 lines)"))
$logPath = Join-Path $env:APPDATA "windows_rectangle\windows_rectangle.log"
if (Test-Path $logPath) {
    [void]$sb.AppendLine("path: $logPath")
    [void]$sb.AppendLine()
    $tail = Get-Content -Path $logPath -Tail 50 -ErrorAction SilentlyContinue
    if ($tail) {
        [void]$sb.AppendLine(($tail -join [Environment]::NewLine))
    } else {
        [void]$sb.AppendLine("(log file is empty)")
    }
} else {
    [void]$sb.AppendLine("(no log file at $logPath)")
}
[void]$sb.AppendLine()

# Build environment.
[void]$sb.AppendLine((Section "environment"))
$osCaption = (Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue).Caption
$osVersion = [Environment]::OSVersion.VersionString
[void]$sb.AppendLine("PSVersion:  $($PSVersionTable.PSVersion)")
[void]$sb.AppendLine("OS:         $osCaption")
[void]$sb.AppendLine("Build:      $osVersion")

# Commit + report.
$sb.ToString() | Set-Content -Path $OutputFile -Encoding utf8
Write-Host ""
Write-Host "==> Doctor report written to:" -ForegroundColor Cyan
Write-Host "    $OutputFile" -ForegroundColor Green
Write-Host ""
Write-Host "Attach the contents to your bug report. Review for anything"
Write-Host "you'd rather not share before posting."

if ($Show) {
    try {
        Invoke-Item -LiteralPath $OutputFile
    } catch {
        Write-Warning ("Could not open file: {0}" -f $_.Exception.Message)
    }
}
