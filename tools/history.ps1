# これまでの保存履歴を見る。戻したいときの手順も表示する。

. (Join-Path $PSScriptRoot "_git.ps1")

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$git = Require-Git

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  保存履歴（新しい順）" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
& $git log --pretty=format:"  %h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" -30
Write-Host ""
Write-Host ""

$dirty = & $git status --porcelain
if ($dirty) {
    Write-Host "  ⚠ まだ保存していない変更があります:" -ForegroundColor Yellow
    & $git status --short
    Write-Host "  → 保存.bat を実行すると記録されます" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "------------------------------------------" -ForegroundColor DarkGray
Write-Host "  昔の状態に戻したいとき" -ForegroundColor Cyan
Write-Host "------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  一番かんたん: GitHub Desktop を開いて、このフォルダを"
Write-Host "  「Add existing repository」で追加すると、履歴も差分も画面で見られます。"
Write-Host ""
Write-Host "  コマンドでやる場合:"
Write-Host "    1) 中身だけ見る          git show <ハッシュ>:ファイル名"
Write-Host "    2) ファイル1つだけ戻す    git checkout <ハッシュ> -- ファイル名"
Write-Host "    3) 全部まるごと戻す       git reset --hard <ハッシュ>"
Write-Host ""
Write-Host "  ※ <ハッシュ> は上の一覧の左端にある7文字の英数字" -ForegroundColor DarkGray
Write-Host "  ※ 3) は今の変更が消えます。先に バックアップ.bat を実行しておくと安心" -ForegroundColor DarkGray
Write-Host ""
Read-Host "  Enter を押すと閉じます"
