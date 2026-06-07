@echo off
REM Run-Dev.bat — quick-launch from source for contributors.
REM Forwards any args (e.g. -Headless, -Python <path>) to Run-Dev.ps1.

setlocal
pushd "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-Dev.ps1" %*
set RC=%ERRORLEVEL%

popd
endlocal & exit /b %RC%
