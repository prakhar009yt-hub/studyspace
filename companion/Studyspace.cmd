@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run Setup.cmd once before opening Studyspace.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" local_companion.py --start
if errorlevel 1 pause
