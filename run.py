# -*- coding: utf-8 -*-
"""
起動スクリプト。

    py -3 run.py              … 自分だけで遊ぶ（localhost:5000）
    py -3 run.py --lan        … 同一LANの他のPC・スマホからも遊べる（ポート80）
    py -3 run.py --port 8080  … ポートを指定する

--lan のときはポート80を使うので、URLから「:5000」を省ける。
（このPCの名前が WISH なので → http://wish/ だけでアクセスできる）
ポート80が他のソフトに使われていた場合は、自動的に5000へ切り替える。
"""
import argparse
import os
import socket
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from server.app import main  # noqa: E402


def port_free(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true",
                    help="LAN内の他のPC・スマホからも接続できるようにする")
    ap.add_argument("--port", type=int, default=None,
                    help="ポート番号（既定は --lan なら80、それ以外は5000）")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    port = args.port if args.port else (80 if args.lan else 5000)

    # ポート80は他のソフト（IISなど）と衝突しやすいので、駄目なら5000へ逃がす
    if not port_free(host, port):
        if args.port is None and port == 80:
            print("  ⚠️ ポート80は別のソフトが使っているため、5000で起動します")
            port = 5000
        else:
            print("  ❌ ポート {} は既に使われています。".format(port))
            print("     すでに開いているゲームの黒い画面を閉じてから、もう一度試してください。")
            print("     別のポートで動かすなら:  py -3 run.py --port 5001")
            input("\n  Enter を押すと閉じます ")
            sys.exit(1)

    if not args.no_browser:
        url = "http://localhost/" if port == 80 else "http://localhost:{}/".format(port)
        webbrowser.open(url)

    try:
        main(host=host, port=port)
    except KeyboardInterrupt:
        print("\n  サーバーを停止しました。またあそんでね！🎴")
    except OSError as e:
        print("\n  ❌ 起動に失敗しました: {}".format(e))
        input("\n  Enter を押すと閉じます ")
