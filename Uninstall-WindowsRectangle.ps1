<#
.SYNOPSIS
    Cleanly remove Windows Rectangle from the current user account.

.DESCRIPTION
    Symmetric counterpart to Build-Exe.ps1's optional Start-Menu shortcut
    + the app's own "Launch at login" registry entry. Does NOT delete the
    .exe (the user owns where they put it), the project source tree, or
    the JSON config — it just removes the bits that "install" leaves in
    the user profile:

      1. Quits any running WindowsRectangle.exe so step 3 can clean up.
      2. Removes the per-user Start-Menu shortcut, if present.
      3. Removes the per-user "Launch at login" registry entry, if present.
      4. Prints the config-folder path so the user can hand-delete it
         later if they want a fully clean uninstall.

    Idempotent — running twice is a no-op.

.PARAMETER PurgeConfig
    Also delete `%APPDATA%\windows_rectangle\` (the config + any logs).
    Off by default to avoid deleting user data unexpectedly.

.EXAMPLE
    .\Uninstall-WindowsRectangle.ps1
    Standard uninstall — shortcut + autostart removed, config kept.

.EXAMPLE
    .\Uninstall-WindowsRectangle.ps1 -PurgeConfig
    Clean uninstall — also delete the JSON config folder.
#>

[CmdletBinding()]
param(
    [switch] $PurgeConfig
)

$ErrorActionPreference = "Stop"

function Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

Step "Stopping any running WindowsRectangle.exe"
$running = @(Get-Process -ErrorAction SilentlyContinue -Name WindowsRectangle)
if ($running.Count -gt 0) {
    foreach ($p in $running) {
        try {
            # CloseMainWindow lets the tray app run its shutdown — unhook
            # mouse, unregister hotkeys, release the mutex (brief §5 #11).
            # If that doesn't take effect within 3s, force-stop.
            if (-not $p.CloseMainWindow()) {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            } else {
                if (-not $p.WaitForExit(3000)) {
                    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
                }
            }
            Write-Host "    Stopped PID $($p.Id)."
        } catch {
            Write-Warning ("Could not stop PID {0}: {1}" -f $p.Id, $_.Exception.Message)
        }
    }
} else {
    Write-Host "    none"
}

Step "Removing Start-Menu shortcut"
$startMenu = [Environment]::GetFolderPath("Programs")
$shortcutPath = Join-Path $startMenu "Windows Rectangle.lnk"
if (Test-Path $shortcutPath) {
    try {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "    $shortcutPath removed." -ForegroundColor Green
    } catch {
        Write-Warning ("Shortcut removal failed: {0}" -f $_.Exception.Message)
    }
} else {
    Write-Host "    (no shortcut found)"
}

Step "Removing 'Launch at login' registry entry"
# The Windows-side WinRegAutoStart adapter writes here; mirror its key
# names so removal is symmetric. See windows_rectangle/adapters/winreg_autostart.py.
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$valueName = "WindowsRectangle"
try {
    $entry = Get-ItemProperty -Path $runKey -Name $valueName -ErrorAction Stop
    Remove-ItemProperty -Path $runKey -Name $valueName -Force
    Write-Host ("    Removed {0}\{1} (was: {2})" -f $runKey, $valueName, $entry.$valueName) -ForegroundColor Green
} catch [System.Management.Automation.ItemNotFoundException] {
    Write-Host "    (no autostart entry found)"
} catch [System.Management.Automation.PSArgumentException] {
    Write-Host "    (no autostart entry found)"
} catch {
    # Fall-through: missing value name on an otherwise-present key.
    Write-Host "    (no autostart entry found)"
}

$configFolder = Join-Path $env:APPDATA "windows_rectangle"
if ($PurgeConfig) {
    Step "Purging config folder"
    if (Test-Path $configFolder) {
        try {
            Remove-Item -LiteralPath $configFolder -Recurse -Force
            Write-Host "    $configFolder removed." -ForegroundColor Green
        } catch {
            Write-Warning ("Could not remove config folder: {0}" -f $_.Exception.Message)
        }
    } else {
        Write-Host "    (no config folder found)"
    }
} else {
    Step "Config folder retained"
    Write-Host "    $configFolder"
    Write-Host "    Pass -PurgeConfig to delete it, or `Remove-Item -Recurse` manually."
}

Step "Done"
Write-Host "    Windows Rectangle is uninstalled from this user account." -ForegroundColor Green
Write-Host "    The .exe and source tree are left in place; delete them manually if you want them gone."
