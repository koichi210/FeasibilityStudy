@echo off
rem ---------------------------------------------------------------
rem  IMPORTANT: Do NOT write Japanese in this file.
rem  After "chcp 65001", cmd.exe loses its read position on
rem  multi-byte characters and starts executing garbage.
rem  The Japanese banner is printed by run.py instead.
rem ---------------------------------------------------------------
chcp 65001 > nul
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py --lan
) else (
    python run.py --lan
)

echo.
pause
