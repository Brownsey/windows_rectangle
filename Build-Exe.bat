@echo off
REM Build-Exe.bat — convenience wrapper around Build-Exe.ps1.
REM
REM Double-click friendly: opens a console window, runs the PowerShell
REM build, then pauses so the user can read the result.
REM
REM Forwards any args to the underlying script — e.g.:
REM     Build-Exe.bat -Clean
REM     Build-Exe.bat -Python "C:\Python311\python.exe"

setlocal
pushd "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Exe.ps1" %*
set RC=%ERRORLEVEL%

popd
echo.
if %RC% NEQ 0 (
    echo Build failed with exit code %RC%.
) else (
    echo Build complete — see dist\WindowsRectangle.exe.
)
pause
endlocal & exit /b %RC%
