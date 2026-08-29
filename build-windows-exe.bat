@echo off
setlocal EnableExtensions

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build-windows.ps1" %*
exit /b %ERRORLEVEL%
