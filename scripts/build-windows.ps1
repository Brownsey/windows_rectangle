[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$SkipChecks,
    [switch]$NoInstall,
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $ScriptDir))

function Resolve-InRepoPath([string]$Path) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    $separators = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd($separators)
    $isRoot = $resolved.Equals($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)
    $isChild = $resolved.StartsWith(
        "$resolvedRoot$([System.IO.Path]::DirectorySeparatorChar)",
        [System.StringComparison]::OrdinalIgnoreCase
    )
    if (-not ($isRoot -or $isChild)) {
        throw "Refusing to operate outside repository: $resolved"
    }
    return $resolved
}

$VenvDir = Resolve-InRepoPath (Join-Path $RepoRoot ".venv")
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

function Test-CommandExists([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Try-CreateVenv([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    return $LASTEXITCODE -eq 0
}

function New-BuildVenv {
    if (Test-Path -LiteralPath $VenvPython) {
        return
    }

    Write-Host "Creating virtual environment in $VenvDir..."
    New-Item -ItemType Directory -Force -Path $VenvDir | Out-Null

    if (Test-CommandExists "py") {
        if (Try-CreateVenv "py" @("-3.11", "-m", "venv", $VenvDir)) {
            return
        }
        if (Try-CreateVenv "py" @("-3", "-m", "venv", $VenvDir)) {
            return
        }
    }

    if (Test-CommandExists "python") {
        if (Try-CreateVenv "python" @("-m", "venv", $VenvDir)) {
            return
        }
    }

    throw "Python 3.11 or newer was not found. Install Python and retry."
}

function Resolve-BuildPython {
    if ($Python) {
        return $Python
    }

    New-BuildVenv
    return $VenvPython
}

function Remove-DirectoryIfPresent([string]$Path) {
    $resolved = Resolve-InRepoPath $Path
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

function Wait-FileReady([string]$Path) {
    $attempts = 120
    for ($i = 1; $i -le $attempts; $i += 1) {
        try {
            $stream = [System.IO.File]::Open(
                $Path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::None
            )
            $stream.Dispose()
            return
        } catch {
            if ($i -eq $attempts) {
                throw "File is still locked after smoke test: $Path"
            }
            Start-Sleep -Milliseconds 500
        }
    }
}

function Wait-DirectoryReady([string]$Path) {
    Get-ChildItem -LiteralPath $Path -File -Recurse |
        ForEach-Object { Wait-FileReady $_.FullName }
}

function First-ExistingFile([string[]]$Paths) {
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            return $path
        }
    }
    return $null
}

if ($env:OS -ne "Windows_NT") {
    throw "Windows executable builds must run on Windows."
}

$Python = Resolve-BuildPython
$ReleaseDir = Resolve-InRepoPath (Join-Path $RepoRoot "apps\windows\exe")
$DistDir = Resolve-InRepoPath (Join-Path $RepoRoot "build\pyinstaller\dist")
$BuildDir = Resolve-InRepoPath (Join-Path $RepoRoot "build\pyinstaller\windows")
$PackageDir = Resolve-InRepoPath (Join-Path $RepoRoot "build\pyinstaller\package")
$SpecDir = Resolve-InRepoPath (Join-Path $RepoRoot "build\pyinstaller\spec")
$EntryPoint = Resolve-InRepoPath (Join-Path $RepoRoot "packaging\windows\WindowsRectangle.py")
$WindowsSource = Resolve-InRepoPath (Join-Path $RepoRoot "apps\windows")
$LogoDir = Resolve-InRepoPath (Join-Path $RepoRoot "logo")
$StopScript = Resolve-InRepoPath (Join-Path $ScriptDir "stop-windows.ps1")
$BuiltAppDir = Join-Path $DistDir "WindowsRectangle"
$BuiltExePath = Join-Path $BuiltAppDir "WindowsRectangle.exe"
$ReleaseExePath = Join-Path $ReleaseDir "WindowsRectangle.exe"
$ChecksumPath = Join-Path $ReleaseDir "WindowsRectangle.exe.sha256"

Push-Location $RepoRoot
try {
    Write-Host "Stopping any running Windows Rectangle instance..."
    & $StopScript -RepoRoot $RepoRoot -Quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stop an existing Windows Rectangle process (exit code $LASTEXITCODE)"
    }

    if (-not $NoInstall) {
        Write-Host "Installing/updating packaging dependencies..."
        Invoke-Native $Python @("-m", "pip", "install", "-e", ".[win,dev,build]") "Dependency installation failed"
    }

    if (-not $SkipChecks) {
        Write-Host "Running quality gate before packaging..."
        & (Join-Path $ScriptDir "check.ps1") -Python $Python
        if ($LASTEXITCODE -ne 0) {
            throw "Quality gate failed (exit code $LASTEXITCODE)"
        }
    }

    if (-not $KeepBuild) {
        Remove-DirectoryIfPresent $DistDir
        Remove-DirectoryIfPresent $BuildDir
        Remove-DirectoryIfPresent $PackageDir
        Remove-DirectoryIfPresent $SpecDir
    }
    Remove-DirectoryIfPresent $ReleaseDir
    New-Item -ItemType Directory -Force -Path $ReleaseDir, $DistDir, $BuildDir, $PackageDir, $SpecDir |
        Out-Null

    $versionOutput = & $Python -c "from windows_rectangle import __version__; print(__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read package version (exit code $LASTEXITCODE)"
    }
    $Version = ([string]$versionOutput).Trim()
    if (-not $Version) {
        throw "Package version was empty"
    }

    $pyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", "WindowsRectangle",
        "--distpath", $DistDir,
        "--workpath", $BuildDir,
        "--specpath", $SpecDir,
        "--paths", $WindowsSource,
        "--hidden-import", "win32timezone",
        $EntryPoint
    )

    if (Test-Path -LiteralPath $LogoDir -PathType Container) {
        $pyInstallerArgs += @("--add-data", "$LogoDir;logo")
    }

    $IconPath = First-ExistingFile @(
        (Join-Path $LogoDir "windows.ico"),
        (Join-Path $LogoDir "logo.ico"),
        (Join-Path $LogoDir "app.ico")
    )
    if ($IconPath) {
        $pyInstallerArgs += @("--icon", $IconPath)
    }

    Write-Host "Building portable executable folder..."
    Invoke-Native $Python $pyInstallerArgs "PyInstaller build failed"

    if (-not (Test-Path -LiteralPath $BuiltExePath)) {
        throw "Expected executable was not produced: $BuiltExePath"
    }

    Copy-Item -Path (Join-Path $BuiltAppDir "*") -Destination $ReleaseDir -Recurse -Force

    Write-Host "Smoke-testing packaged executable..."
    Invoke-Native $ReleaseExePath @("--version") "Packaged executable smoke test failed"
    Wait-DirectoryReady $ReleaseDir

    $hash = (Get-FileHash -LiteralPath $ReleaseExePath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $ChecksumPath -Value "$hash  WindowsRectangle.exe" -Encoding ASCII
    Wait-DirectoryReady $ReleaseDir

    $platform = if ([Environment]::Is64BitProcess) { "windows-x64" } else { "windows-x86" }
    $ZipPath = Join-Path $ReleaseDir "WindowsRectangle-$Version-$platform.zip"
    $ZipChecksumPath = "$ZipPath.sha256"
    $PackageAppDir = Join-Path $PackageDir "WindowsRectangle"

    New-Item -ItemType Directory -Force -Path $PackageAppDir | Out-Null
    Copy-Item -Path (Join-Path $ReleaseDir "*") -Destination $PackageAppDir -Recurse -Force
    Wait-DirectoryReady $PackageAppDir

    Compress-Archive -LiteralPath $PackageAppDir -DestinationPath $ZipPath -Force
    Wait-FileReady $ZipPath
    $zipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $zipName = Split-Path -Leaf $ZipPath
    Set-Content -LiteralPath $ZipChecksumPath -Value "$zipHash  $zipName" -Encoding ASCII

    $item = Get-Item -LiteralPath $ReleaseExePath
    $sizeMb = [Math]::Round($item.Length / 1MB, 1)
    Write-Host ""
    Write-Host "Built $ReleaseExePath ($sizeMb MB)"
    Write-Host "Created $ChecksumPath"
    Write-Host "Created $ZipPath"
    Write-Host "Created $ZipChecksumPath"
    Write-Host "Share the zip or the full apps\windows\exe folder; Python and dependencies are bundled."
} finally {
    Pop-Location
}
