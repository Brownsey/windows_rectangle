<#
.SYNOPSIS
    Compatibility launcher for the canonical portable Windows build.
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$Clean,
    [switch]$NoInstall,
    [switch]$InstallStartMenuShortcut,
    [switch]$Launch
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
# The canonical build cleans by default; -Clean is retained for existing callers.
& (Join-Path $repo "scripts/build-windows.ps1") -Python $Python -NoInstall:$NoInstall
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$exe = Join-Path $repo "apps/windows/exe/WindowsRectangle.exe"
if ($InstallStartMenuShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Programs")) "Windows Rectangle.lnk"))
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = Split-Path -Parent $exe
    $shortcut.Description = "Windows Rectangle window manager"
    $shortcut.Save()
}
if ($Launch) { Start-Process -FilePath $exe -WindowStyle Hidden }
