@echo off
chcp 65001 > nul
cd /d "%~dp0"

rem py ランチャーがある環境ではそれを使い、無ければ python を使う。
rem （オグさんのPCでは python がWindowsストアのダミーに繋がるため py を優先する）
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py
) else (
    python run.py
)

echo.
echo   ---- 終了しました ----
echo   エラーが出ていたら docs\05_はじめかた（共同開発者へ）.md を見てください。
echo.
pause
