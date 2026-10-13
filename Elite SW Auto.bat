@echo off
REM Created by Tanzim Nasir
REM Copyright (c) 2026 Elite Integrity Services.
REM Opens the GUI with no console when pythonw is available.
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0Elite SW Auto.pyw"
  exit /b 0
)
python "%~dp0Elite SW Auto.pyw"
if errorlevel 1 pause
