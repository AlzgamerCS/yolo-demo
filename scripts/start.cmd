@echo off
cd /d "%~dp0.."
if not exist ".venv-system\Scripts\python.exe" (
    echo Run setup.ps1 first to install the environment.
    pause
    exit /b 1
)
".venv-system\Scripts\python.exe" -m yolo_studio.desktop %*
if errorlevel 1 pause
