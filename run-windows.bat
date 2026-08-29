@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "MODE=%~1"

if "%MODE%"=="" set "MODE=run"

if /I "%MODE%"=="help" goto :usage
if /I "%MODE%"=="--help" goto :usage
if /I "%MODE%"=="/?" goto :usage
if /I "%MODE%"=="stop" goto :stop_only
if /I "%MODE%"=="build" goto :build_exe
if /I "%MODE%"=="package" goto :build_exe
if /I "%MODE%"=="exe" goto :build_exe

call :stop_existing
if errorlevel 1 goto :error

if not exist "%PYTHON_EXE%" (
    echo Creating virtual environment in %VENV_DIR%...
    call :create_venv
    if errorlevel 1 goto :error
)

echo Installing/updating Windows Rectangle dependencies...
"%PYTHON_EXE%" -m pip install -e ".[win,dev]"
if errorlevel 1 goto :error

if /I "%MODE%"=="run" goto :run_with_preferences
if /I "%MODE%"=="app" goto :run_with_preferences
if /I "%MODE%"=="preferences" goto :run_with_preferences
if /I "%MODE%"=="prefs" goto :run_with_preferences
if /I "%MODE%"=="tray" goto :run_app
if /I "%MODE%"=="headless" goto :run_headless
if /I "%MODE%"=="check" goto :check
if /I "%MODE%"=="test" goto :test

echo Unknown mode: %MODE%
goto :usage_error

:stop_only
call :stop_existing
if errorlevel 1 goto :error
goto :done

:stop_existing
echo Stopping any existing Windows Rectangle instance...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\stop-windows.ps1" -RepoRoot "%CD%"
exit /b %ERRORLEVEL%

:run_with_preferences
echo Starting Windows Rectangle preferences...
"%PYTHON_EXE%" -m windows_rectangle --open-preferences
if errorlevel 1 goto :error
goto :done

:run_app
echo Starting Windows Rectangle...
"%PYTHON_EXE%" -m windows_rectangle --tray
if errorlevel 1 goto :error
goto :done

:run_headless
echo Starting Windows Rectangle headless...
"%PYTHON_EXE%" -m windows_rectangle --headless
if errorlevel 1 goto :error
goto :done

:check
echo Running lint, format check, type check, and tests...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\check.ps1" -Python "%PYTHON_EXE%"
if errorlevel 1 goto :error
goto :done

:test
echo Running tests...
"%PYTHON_EXE%" -m pytest
if errorlevel 1 goto :error
goto :done

:build_exe
echo Building shareable Windows Rectangle executable...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build-windows.ps1"
if errorlevel 1 goto :error
goto :done

:create_venv
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -m venv "%VENV_DIR%" && exit /b 0
    py -3 -m venv "%VENV_DIR%" && exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.11 or newer and retry.
    exit /b 1
)

python -m venv "%VENV_DIR%"
exit /b %ERRORLEVEL%

:usage
echo.
echo Windows Rectangle launcher
echo.
echo Usage:
echo   run-windows.bat            Set up dependencies and open the preferences window
echo   run-windows.bat run        Same as above
echo   run-windows.bat prefs      Same as above
echo   run-windows.bat tray       Run the tray app without opening preferences
echo   run-windows.bat headless   Run without the tray UI
echo   run-windows.bat check      Run lint, format check, mypy, and tests
echo   run-windows.bat test       Run tests only
echo   run-windows.bat build      Build apps\windows\exe\WindowsRectangle.exe
echo   run-windows.bat stop       Stop existing Windows Rectangle instances
echo.
exit /b 0

:usage_error
call :usage
exit /b 1

:error
echo.
echo Windows Rectangle command failed.
echo.
pause
exit /b 1

:done
endlocal
