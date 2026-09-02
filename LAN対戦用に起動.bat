@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo.
echo   このPC = サーバーになります。
echo   ほかのPCのブラウザから、下に表示される IP アドレスで接続してください。
echo.
echo   ---- このPCの IP アドレス ----
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { '     http://' + $_.IPAddress + ':5000/' }"
echo   ------------------------------
echo.
py -3 run.py --lan --no-browser
echo.
pause
