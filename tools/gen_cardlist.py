# -*- coding: utf-8 -*-
"""
カードリストのドキュメントを、実際のコード／balance.json から自動生成する。

    py -3 tools\gen_cardlist.py

手書きで表を作るとバランス調整のたびにズレるので、
docs/03_カードリスト.md は必ずこれで作り直すこと。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from engine.cards import (BALANCE, SUITS, SUIT_MARK, SUIT_NAME, RANKS,  # noqa: E402
                          build_item_deck, build_enemy_deck, rank_label)

OUT = os.path.join(ROOT, "docs", "03_カードリスト.md")

SUIT_ROLE = {
    "S": "高火力・ハイリスク",
    "H": "回復・防御",
    "D": "攻撃",
    "C": "戦術",
}


def main():
    enemies = {c.code: c for c in build_enemy_deck()}
    items = {c.code: c for c in build_item_deck()}
    B = BALANCE

    L = []
    a = L.append
    a("# 🃏 カードリスト（全52種）")
    a("")
    a("> ⚠️ **このファイルは自動生成です。手で編集しないでください。**")
    a("> `balance.json` を変更したら `py -3 tools\\gen_cardlist.py` で作り直してください。")
    a("")
    a("エネミーとアイテムは同じ「トランプ1箱」の読み替えです。")
    a("同じ ♠K でも、エネミーデッキから出れば「暴君」、アイテムデッキから出れば「生贄の儀式」になります。")
    a("")
    a("## 共通ルールの数値")
    a("")
    a("| 項目 | 値 |")
    a("|---|---|")
    a("| トレーナーHP | {} |".format(B["trainer_hp"]))
    a("| エネミーHP（全員共通） | {} |".format(B["enemy_hp"]))
    a("| 最低保証ダメージ | {} |".format(B["min_damage"]))
    a("| エネミー撃破時のトレーナーダメージ | {} |".format(B["kill_trainer_damage"]))
    a("| ベンチ枚数 | {} |".format(B["bench_size"]))
    a("| 手札上限（アイテム） | {} |".format(B["hand_size_max"]))
    a("| 強制退場までの攻撃回数 | {} |".format(B["attacks_before_retire"]))
    a("")
    a("### 数字カードのステータス計算式")
    a("")
    a("```")
    a("攻撃力 = 数字 × {} + スート補正".format(B["rank_base_multiplier"]))
    a("防御力 = 数字 × {} + スート補正   （最低 {}）".format(
        B["rank_base_multiplier"], B["stat_min"]))
    a("```")
    a("")
    a("| スート | 役割 | 攻撃補正 | 防御補正 |")
    a("|---|---|---|---|")
    for s in SUITS:
        m = B["suit_modifier"][s]
        a("| {} {} | {} | {:+d} | {:+d} |".format(
            SUIT_MARK[s], SUIT_NAME[s], SUIT_ROLE[s], m["atk"], m["def"]))
    a("")
    a("J=11、Q=12、K=13 として同じ式で計算します。A だけ個別設定です。")
    a("")
    a("---")
    a("")

    # ---------------- エネミー ----------------
    a("## ⚔️ エネミーカード")
    a("")
    for s in SUITS:
        a("### {} {}（{}）".format(SUIT_MARK[s], SUIT_NAME[s], SUIT_ROLE[s]))
        a("")
        a("| カード | 名前 | ⚔️攻撃 | 🛡️防御 | ✨技 |")
        a("|---|---|---:|---:|---|")
        for r in RANKS:
            c = enemies[s + rank_label(r)]
            ab = c.ability.text if c.ability else "—"
            name = c.name
            if c.ability:
                name = "**{}**".format(name)
            a("| {}{} | {} | {} | {} | {} |".format(
                SUIT_MARK[s], rank_label(r), name, c.atk, c.dfn, ab))
        a("")

    a("### 👹 魔王（♠A の「魔王降臨」で登場）")
    a("")
    d = B["demon_lord"]
    a("| HP | 攻撃 | 防御 | 存在ターン | 制約 |")
    a("|---:|---:|---:|---:|---|")
    a("| {} | {} | {} | {} | 魔王同士は攻撃できない |".format(
        d["hp"], d["atk"], d["def"], d["turns"]))
    a("")
    a("---")
    a("")

    # ---------------- アイテム ----------------
    a("## 🎒 アイテムカード")
    a("")
    a("アイテムデッキは **両プレイヤーで共有の1箱** です。1ターンに1枚まで使えます。")
    a("")
    for s in SUITS:
        a("### {} {}".format(SUIT_MARK[s], SUIT_NAME[s]))
        a("")
        a("| カード | 名前 | 効果 |")
        a("|---|---|---|")
        for r in RANKS:
            c = items[s + rank_label(r)]
            a("| {}{} | {} | {} |".format(
                SUIT_MARK[s], rank_label(r), c.name, c.effect.text))
        a("")

    text = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("✅ 生成しました → {}".format(OUT))
    print("   エネミー {} 種 / アイテム {} 種".format(len(enemies), len(items)))


if __name__ == "__main__":
    main()
