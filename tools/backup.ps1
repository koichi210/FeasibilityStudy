# プロジェクトを zip でスナップショット保存する。
#   _backups\card-game_20260902-2249.zip  みたいなファイルが1個できる。
# フォルダを丸ごとコピーするのと違って、1ファイルなので
# Google Drive の同期も軽く、フォルダ一覧も散らからない。

$ErrorActionPreference = "Stop"
$root      = Split-Path -Parent $PSScriptRoot
$stamp     = Get-Date -Format "yyyyMMdd-HHmm"
$backupDir = Join-Path $root "_backups"
$zipPath   = Join-Path $backupDir "card-game_$stamp.zip"
$keep      = 20   # 直近この数だけ残して、古いものは自動で消す

if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

# 一時フォルダにコピーしてから固める（不要なフォルダを除外するため）
$tmp = Join-Path $env:TEMP "cardgame_backup_$stamp"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }

Write-Host ""
Write-Host "  ファイルを集めています..." -ForegroundColor Cyan
robocopy $root $tmp /E /XD "_backups" "__pycache__" ".git" ".venv" "venv" /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "  コピーに失敗しました (robocopy exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

Write-Host "  zip に固めています..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $tmp "*") -DestinationPath $zipPath -Force
Remove-Item $tmp -Recurse -Force

$size = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)
Write-Host ""
Write-Host "  バックアップ完了" -ForegroundColor Green
Write-Host "    $zipPath  ($size KB)"

# 古いバックアップを整理
$all = Get-ChildItem $backupDir -Filter "card-game_*.zip" | Sort-Object Name -Descending
if ($all.Count -gt $keep) {
    $old = $all | Select-Object -Skip $keep
    $old | Remove-Item -Force
    Write-Host "    古いバックアップ $($old.Count) 件を削除しました（直近 $keep 件を保持）" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  いま保存されているバックアップ:" -ForegroundColor Cyan
Get-ChildItem $backupDir -Filter "card-game_*.zip" |
    Sort-Object Name -Descending |
    Select-Object -First 8 |
    ForEach-Object { "    {0}  ({1} KB)" -f $_.Name, [math]::Round($_.Length / 1KB, 1) }
Write-Host ""
