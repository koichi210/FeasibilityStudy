# -*- coding: utf-8 -*-
"""
起動スクリプト。

    py -3 run.py              … 自分だけで遊ぶ（localhost）
    py -3 run.py --lan        … 同一LANの他のPCからも見える（将来の対戦用）
    py -3 run.py --port 8080  … ポート変更
"""
import argparse
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows のコンソールは既定が cp932 なので、絵文字入りの表示が文字化けする
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from server.app import main  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="LAN内の他PCからも接続できるようにする")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    if not args.no_browser:
        webbrowser.open("http://localhost:{}/".format(args.port))
    main(host=host, port=args.port)
