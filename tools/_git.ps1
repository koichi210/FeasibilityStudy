# git.exe の場所を探す共通処理。
#
# このPCには Git 単体がインストールされていないが、GitHub Desktop に git が同梱されている。
# インストール作業なしで使えるので、それを探して利用する。
# （GitHub Desktop を更新するとフォルダ名が変わるため、毎回探し直す）

function Get-GitExe {
    # 1) PATH に git があればそれを使う
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # 2) Git for Windows の標準インストール先
    foreach ($p in @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
    )) {
        if (Test-Path $p) { return $p }
    }

    # 3) GitHub Desktop の同梱 git（新しいバージョンから順に探す）
    $ghRoot = Join-Path $env:LOCALAPPDATA "GitHubDesktop"
    if (Test-Path $ghRoot) {
        $apps = Get-ChildItem $ghRoot -Filter "app-*" -Directory -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending
        foreach ($d in $apps) {
            $p = Join-Path $d.FullName "resources\app\git\cmd\git.exe"
            if (Test-Path $p) { return $p }
        }
    }

    return $null
}

function Require-Git {
    $git = Get-GitExe
    if (-not $git) {
        Write-Host ""
        Write-Host "  git が見つかりませんでした。" -ForegroundColor Red
        Write-Host ""
        Write-Host "  対処法のどちらかを試してください:" -ForegroundColor Yellow
        Write-Host "    A) GitHub Desktop を起動する（同梱のgitが使えるようになります）"
        Write-Host "    B) https://git-scm.com/download/win から Git for Windows を入れる"
        Write-Host ""
        Write-Host "  なお git が無くても「バックアップ.bat」（zip保存）は使えます。" -ForegroundColor Cyan
        Write-Host ""
        Read-Host "  Enter を押すと閉じます"
        exit 1
    }
    return $git
}
