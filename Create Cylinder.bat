@echo off
REM Created by Tanzim Nasir
REM Copyright (c) 2026 Elite Integrity Services.
REM Developed for Elite Integrity Services by Tanzim Nasir.
REM Unauthorized use by other companies is prohibited.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
echo Computer: %COMPUTERNAME%
echo Create a solid cylinder in SolidWorks (leave SolidWorks open)...
echo.
python -m swauto cylinder %*
if errorlevel 1 (
  echo.
  echo Run this on the computer named Solidworks, after SolidWorks is open.
  echo Example:  Create Cylinder.bat --diameter 24 --height 48 --unit in
  echo.
)
pause
