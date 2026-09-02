@echo off
chcp 65001 > nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\show_ip.ps1"
py -3 run.py --lan --no-browser
echo.
pause
