@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 local_companion.py --install
) else (
    python local_companion.py --install
)
if errorlevel 1 echo Setup failed. Install Python 3.11 or newer from https://www.python.org/downloads/windows/ and try again.
pause
