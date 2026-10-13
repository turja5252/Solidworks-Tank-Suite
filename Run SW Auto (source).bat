@echo off
REM Created by Tanzim Nasir
REM Copyright (c) 2026 Elite Integrity Services.
REM Developed for Elite Integrity Services by Tanzim Nasir.
REM Unauthorized use by other companies is prohibited.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
echo Computer: %COMPUTERNAME%
echo Checking SolidWorks in this Windows session...
python -m swauto status
if errorlevel 1 (
  echo.
  echo Run this on the computer named Solidworks, after SolidWorks is open.
  echo If Python is missing, install 64-bit Python 3.11 or newer from python.org.
  echo If pywin32 is missing, run:  python -m pip install pywin32
  echo.
  pause
)
