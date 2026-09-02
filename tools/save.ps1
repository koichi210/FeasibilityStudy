# 作業内容を git に保存する（コミットする）。
# git を知らなくても、これをダブルクリックするだけで「その時点の状態」が丸ごと記録される。

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "_git.ps1")

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$git = Require-Git

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  作業内容を保存します" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$changes = & $git status --porcelain
if (-not $changes) {
    Write-Host "  前回の保存から変更はありません。何もしませんでした。" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Enter を押すと閉じます"
    exit 0
}

Write-Host "  今回保存される変更:" -ForegroundColor Green
& $git status --short
Write-Host ""

$msg = Read-Host "  何をした？（空欄でもOK）"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
if ([string]::IsNullOrWhiteSpace($msg)) {
    $msg = "作業保存 $stamp"
} else {
    $msg = "$msg ($stamp)"
}

& $git add -A
& $git commit -m $msg | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "  保存しました: $msg" -ForegroundColor Green
    Write-Host ""
    Write-Host "  最近の保存履歴:" -ForegroundColor Cyan
    & $git log --oneline -8 | ForEach-Object { "    $_" }
} else {
    Write-Host ""
    Write-Host "  保存に失敗しました。上のメッセージを確認してください。" -ForegroundColor Red
}

Write-Host ""
Read-Host "  Enter を押すと閉じます"
