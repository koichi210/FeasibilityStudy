# -*- coding: utf-8 -*-
"""
全スキン分のカード図鑑データを、実際のコード／balance.json/skins/*.json から
まとめて自動生成する。

    py -3 tools\\gen_codex_data.py

web/codex.html（ゲーム内の「📖 図鑑」からリンクしている全スキン版の図鑑）が
web/codex_data.json を読み込んで表示する。ここが古いままだと図鑑の内容が
実際のカードとズレてしまうので、**スキンやバランスを変えたら必ず作り直すこと**。

⚠️ 実装メモ：
  engine.cards.apply_skin() はモジュール内の辞書を「その場で」書き換える方式
  （server/app.py が動いている本物のサーバープロセスにも同じ仕組みで効く）。
  このスクリプトは実行してすぐ終わる**別プロセス**なので、
  遊んでいる最中のサーバーには一切影響しない。安全にいつでも実行できる。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from engine import skins as skin_store              # noqa: E402
from engine import cards as cards_mod                # noqa: E402
from engine.reference import build_reference         # noqa: E402

OUT = os.path.join(ROOT, "web", "codex_data.json")


def main():
    skin_list = skin_store.available_skins()
    out = []
    for s in skin_list:
        cards_mod.apply_skin(s["id"])
        out.append({"id": s["id"], "label": s["label"], "ref": build_reference()})

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"skins": out}, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    # 起動時デフォルトのスキンに戻す（このプロセスはもう終わるので実質不要だが、念のため）
    cards_mod.apply_skin()

    print("✅ {} 個のスキン分を書き出したよ → {}".format(len(out), OUT))
    for s in skin_list:
        print("   - {} ({})".format(s["label"], s["id"]))


if __name__ == "__main__":
    main()
