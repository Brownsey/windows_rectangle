<#
.SYNOPSIS
    Build a single-file WindowsRectangle.exe from the source tree.

.DESCRIPTION
    One-shot build script for end users:
      1. Resolves the Python interpreter to use (`-Python` overrides; falls
         back to the system `python` on PATH).
      2. Verifies the runtime extras (PySide6, pywin32) and PyInstaller are
         installed; auto-installs anything missing.
      3. Invokes PyInstaller against the hand-tuned `windows_rectangle.spec`.
      4. Reports the path to the produced binary (`dist\WindowsRectangle.exe`).

    No admin rights required — the install is `pip install --user` if the
    interpreter is the system Python, otherwise into whatever environment
    that interpreter resolves to (use a venv if you want isolation).

.PARAMETER Python
    Path to a Python 3.11+ executable. Defaults to `python` on PATH.

.PARAMETER Clean
    Pass --clean to PyInstaller (removes the build/ cache first).

.PARAMETER NoInstall
    Skip the dependency-install step. Useful if you've already installed
    PyInstaller + the win extras and don't want pip to re-resolve.

.EXAMPLE
    .\Build-Exe.ps1
    Builds with the default Python.

.EXAMPLE
    .\Build-Exe.ps1 -Python "C:\Users\Me\.venvs\winrect\Scripts\python.exe" -Clean
    Builds inside a venv with a fresh build/ cache.
#>

[CmdletBinding()]
param(
    [string] $Python = "python",
    [switch] $Clean,
    [switch] $NoInstall
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

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
    Step "Ensuring runtime + build dependencies are installed"
    # The win extras (PySide6, pywin32) match what the bundled .exe needs;
    # PyInstaller is what actually produces the binary. Run pip in one call
    # so resolver work happens once.
    & $Python -m pip install --upgrade `
        "pyinstaller>=6.0" `
        "PySide6>=6.6" `
        "pywin32>=306"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed (exit $LASTEXITCODE)."
        exit $LASTEXITCODE
    }
} else {
    Write-Host "    Skipping (-NoInstall)."
}

Step "Running PyInstaller"
$pyinstallerArgs = @("-m", "PyInstaller", "windows_rectangle.spec", "--noconfirm")
if ($Clean) { $pyinstallerArgs += "--clean" }
& $Python @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$exePath = Join-Path $here "dist\WindowsRectangle.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build reported success but $exePath is missing."
    exit 1
}

$size = (Get-Item $exePath).Length / 1MB
Step "Done"
Write-Host ("    {0}  ({1:N1} MB)" -f $exePath, $size) -ForegroundColor Green
Write-Host "    Double-click to launch, or copy somewhere on PATH."
