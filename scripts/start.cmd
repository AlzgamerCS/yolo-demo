@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv-system\Scripts\python.exe" (
    echo Run setup.ps1 first to install the environment.
    pause
    exit /b 1
)
rem Prefer this checkout even when an editable installation points to an old location.
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
".venv-system\Scripts\python.exe" -m yolo_studio.desktop %*
if errorlevel 1 pause
