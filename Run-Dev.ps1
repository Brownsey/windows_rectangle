<#
.SYNOPSIS
    Run Windows Rectangle from source (no .exe build) for development.

.DESCRIPTION
    Quick-path for contributors:
      1. Verifies the chosen Python interpreter exists.
      2. Auto-installs the app and Qt if missing (skipped
         with -NoInstall).
      3. Runs `python -m windows_rectangle` so the tray icon appears.

    For full setup (editable install + dev tools like pytest/ruff/mypy)
    use `pip install -e ".[dev,win]"` directly. This script is the
    fast path that gets the tray running.

.PARAMETER Python
    Path to a Python 3.11+ executable. Defaults to `python` on PATH.

.PARAMETER NoInstall
    Skip the dependency-install step.

.PARAMETER Headless
    Forward `--headless` to the app (hotkeys + dispatcher only, no Qt).

.PARAMETER LogLevel
    Forwarded as `--log-level <value>`. One of DEBUG/INFO/WARNING/ERROR.
#>

[CmdletBinding()]
param(
    [string] $Python = "",
    [switch] $NoInstall,
    [switch] $Headless,
    [ValidateSet("DEBUG", "INFO", "WARNING", "ERROR")]
    [string] $LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
if (-not $Python) {
    $localPython = Join-Path $here ".venv\Scripts\python.exe"
    $Python = if (Test-Path -LiteralPath $localPython) { $localPython } else { "python" }
}

function Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

Step "Resolving Python"
try {
    $version = & $Python --version 2>&1
} catch {
    Write-Error "Could not invoke '$Python'. Install Python 3.11+ or pass -Python <path>."
    exit 1
}
Write-Host "    $version"

if (-not $NoInstall) {
    # Probe rather than blindly running pip — keeps repeat launches fast.
    # If either probe fails we install both; resolver work happens once.
    $missing = $false
    & $Python -c "import windows_rectangle.__main__, PySide6.QtWidgets" 2>$null
    if ($LASTEXITCODE -ne 0) { $missing = $true }
    if ($missing) {
        Step "Installing Windows Rectangle and Qt"
        & $Python -m pip install "-e" ".[win,dev]"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "pip install failed (exit $LASTEXITCODE)."
            exit $LASTEXITCODE
        }
    } else {
        Step "Runtime deps already installed — skipping pip"
    }
}

Step "Launching Windows Rectangle"
$args = @("-m", "windows_rectangle", "--log-level", $LogLevel)
if ($Headless) { $args += "--headless" }
Write-Host "    $Python $($args -join ' ')"
& $Python @args
exit $LASTEXITCODE
