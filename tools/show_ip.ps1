# LAN対戦のときに、他のPCから入力してもらうURLを表示する。

Write-Host ""
Write-Host "  ==== ほかのPCのブラウザで、このURLを開いてください ====" -ForegroundColor Cyan
Write-Host ""

$found = $false
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Sort-Object InterfaceMetric |
    ForEach-Object {
        $found = $true
        Write-Host ("      http://" + $_.IPAddress + ":5000/") -ForegroundColor Yellow -NoNewline
        Write-Host ("    ( " + $_.InterfaceAlias + " )") -ForegroundColor DarkGray
    }

if (-not $found) {
    Write-Host "      ネットワークに接続されていないようです" -ForegroundColor Red
}

Write-Host ""
Write-Host "  ※ 複数出た場合は、Wi-Fi または イーサネット のものを使ってください" -ForegroundColor DarkGray
Write-Host "  ※ 初回はWindowsファイアウォールの確認が出ます。「アクセスを許可する」を選んでください" -ForegroundColor DarkGray
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host ""
