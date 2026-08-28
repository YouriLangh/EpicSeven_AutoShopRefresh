@echo off
REM Starts the shop refresher and its dashboard together.
REM Double-click this, or run it from a terminal.
cd /d "%~dp0"
py -3.9 fullScreenTest.py
echo.
pause
