@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Install this project first using the steps in README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" companion/local_companion.py --start
if errorlevel 1 pause
