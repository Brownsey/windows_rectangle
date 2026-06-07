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

.PARAMETER InstallStartMenuShortcut
    After a successful build, drop a "Windows Rectangle.lnk" shortcut into
    the current user's Start Menu Programs folder so the app is findable
    via the Start menu / search. Idempotent — re-running just refreshes
    the target.

.EXAMPLE
    .\Build-Exe.ps1
    Builds with the default Python.

.EXAMPLE
    .\Build-Exe.ps1 -Python "C:\Users\Me\.venvs\winrect\Scripts\python.exe" -Clean
    Builds inside a venv with a fresh build/ cache.

.EXAMPLE
    .\Build-Exe.ps1 -InstallStartMenuShortcut
    Build and add a Start-Menu shortcut for the current user.
#>

[CmdletBinding()]
param(
    [string] $Python = "python",
    [switch] $Clean,
    [switch] $NoInstall,
    [switch] $InstallStartMenuShortcut
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

Step "Checking for a running WindowsRectangle.exe"
# PyInstaller can't overwrite a locked exe — fail fast with a friendly
# error instead of a mid-build PermissionError. We match on the process
# name because the .exe path can differ between -onefile and -onedir.
$running = @(Get-Process -ErrorAction SilentlyContinue -Name WindowsRectangle)
if ($running.Count -gt 0) {
    Write-Error @"
A WindowsRectangle.exe process is already running (PID(s): $($running.Id -join ', ')).
PyInstaller cannot overwrite the locked file. Quit the app via its tray
icon (right-click → Quit) and re-run this script.
"@
    exit 1
}
Write-Host "    none"

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

if ($InstallStartMenuShortcut) {
    Step "Installing Start Menu shortcut"
    # Per-user Programs folder — no elevation needed; survives reboots and
    # is what `Win` key search indexes.
    $startMenu = [Environment]::GetFolderPath("Programs")
    $shortcutPath = Join-Path $startMenu "Windows Rectangle.lnk"
    try {
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($shortcutPath)
        $lnk.TargetPath = $exePath
        $lnk.WorkingDirectory = Split-Path -Parent $exePath
        $lnk.Description = "Windows Rectangle — Rectangle-for-Windows window manager"
        $lnk.Save()
        Write-Host "    $shortcutPath" -ForegroundColor Green
    } catch {
        Write-Warning ("Shortcut creation failed: {0}" -f $_.Exception.Message)
    }
}
