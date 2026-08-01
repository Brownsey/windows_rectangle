[CmdletBinding()]
param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

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

if (-not $Python) {
    $VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $Python = $VenvPython
    } else {
        $Python = "python"
    }
}

Push-Location $RepoRoot
try {
    Invoke-Native $Python @("-m", "ruff", "check", "apps/windows") "Ruff lint failed"
    Invoke-Native $Python @("-m", "ruff", "format", "--check", "apps/windows") "Ruff format check failed"
    Invoke-Native $Python @("-m", "mypy") "Mypy failed"
    Invoke-Native $Python @("-m", "pytest") "Pytest failed"
} finally {
    Pop-Location
}
