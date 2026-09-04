# -*- coding: utf-8 -*-
"""
カード図鑑のデータを組み立てる。

画面（タブ／別ページ）とドキュメント生成の両方から使う。
実際のカード定義と balance.json から作るので、**表示が実装とズレることがない**。

見せ方の方針:
  52枚をそのまま並べても覚えられない。
  数字カードはスートごとに規則的なので「4つの規則 ＋ 絵札16枚」の構造で見せる。
"""
from __future__ import annotations

from typing import Dict, List

from .cards import (BALANCE, RANKS, SUIT_MARK, SUIT_NAME, SUITS,
                    build_item_deck, build_monster_deck, rank_label)

B = BALANCE

SUIT_ROLE = {
    "S": "高火力・ハイリスク",
    "H": "回復・防御",
    "D": "攻撃",
    "C": "戦術",
}

SUIT_HINT = {
    "S": "火力は最強だが打たれ弱い。自分にダメージが返ってくる技も多い",
    "H": "硬い。回復手段を持つので粘り強く戦える",
    "D": "素直な殴り役。攻撃寄りのステータス",
    "C": "攻防は平均的。ドローや妨害で盤面を動かす",
}

ITEM_SUIT_ROLE = {
    "S": "禁断（相手を攻撃）",
    "H": "回復",
    "D": "武器（攻撃を上げる）",
    "C": "防具（防御を上げる）",
}

FACE_RANKS = [11, 12, 13, 14]
NUMBER_RANKS = [r for r in RANKS if r not in FACE_RANKS]


def _card_row(c) -> dict:
    d = {
        "code": c.code,
        "label": c.label,
        "mark": SUIT_MARK[c.suit],
        "suit": c.suit,
        "rank": c.rank,
        "rank_label": rank_label(c.rank),
        "name": c.name,
    }
    if c.kind == "monster":
        d["atk"] = c.atk
        d["dfn"] = c.dfn
        d["ability"] = ({"name": c.ability.name, "text": c.ability.text}
                        if c.ability else None)
    else:
        d["text"] = c.effect.text
        d["effect_type"] = c.effect.type
    return d


def _monster_suit_rules() -> List[dict]:
    """スートごとの性格と、数字カードの計算式。"""
    mult = B["rank_base_multiplier"]
    out = []
    for s in SUITS:
        mod = B["suit_modifier"][s]

        def fmt(v):
            if v == 0:
                return "数字×{}".format(mult)
            return "数字×{} {} {}".format(mult, "＋" if v > 0 else "－", abs(v))

        out.append({
            "suit": s,
            "mark": SUIT_MARK[s],
            "name": SUIT_NAME[s],
            "role": SUIT_ROLE[s],
            "hint": SUIT_HINT[s],
            "atk_formula": fmt(mod["atk"]),
            "def_formula": fmt(mod["def"]),
        })
    return out


def _item_suit_rules() -> List[dict]:
    """アイテムの数字カードは4つの規則で全部説明できる。"""
    iv = B["item_values"]
    return [
        {"suit": "H", "mark": "♥", "name": SUIT_NAME["H"], "role": ITEM_SUIT_ROLE["H"],
         "rule": "バトル場のHPを 数字×{} 回復".format(iv["heal_per_rank"]),
         "example": "♥7 なら {}回復".format(7 * iv["heal_per_rank"])},
        {"suit": "D", "mark": "♦", "name": SUIT_NAME["D"], "role": ITEM_SUIT_ROLE["D"],
         "rule": "攻撃 ＋数字×{}（装備・退場まで有効）".format(iv["weapon_per_rank"]),
         "example": "♦7 なら 攻撃+{}".format(7 * iv["weapon_per_rank"])},
        {"suit": "C", "mark": "♣", "name": SUIT_NAME["C"], "role": ITEM_SUIT_ROLE["C"],
         "rule": "防御 ＋数字×{}（装備・退場まで有効）".format(iv["armor_per_rank"]),
         "example": "♣7 なら 防御+{}".format(7 * iv["armor_per_rank"])},
        {"suit": "S", "mark": "♠", "name": SUIT_NAME["S"], "role": ITEM_SUIT_ROLE["S"],
         "rule": "相手バトル場に 数字×{} ダメージ／自分にも 数字×{}".format(
             iv["burn_per_rank"], iv["burn_recoil_per_rank"]),
         "example": "♠7 なら 相手に{} / 自分に{}".format(
             7 * iv["burn_per_rank"], 7 * iv["burn_recoil_per_rank"])},
    ]


def build_reference() -> dict:
    monsters = {c.code: c for c in build_monster_deck()}
    items = {c.code: c for c in build_item_deck()}

    def group(src, ranks):
        out = []
        for s in SUITS:
            out.append({
                "suit": s,
                "mark": SUIT_MARK[s],
                "name": SUIT_NAME[s],
                "role": SUIT_ROLE[s] if src is monsters else ITEM_SUIT_ROLE[s],
                "cards": [_card_row(src[s + rank_label(r)]) for r in ranks],
            })
        return out

    d = B["demon_lord"]
    return {
        "constants": {
            "trainer_hp": B["trainer_hp"],
            "monster_hp": B["monster_hp"],
            "min_damage": B["min_damage"],
            "kill_trainer_damage": B["kill_trainer_damage"],
            "bench_size": B["bench_size"],
            "hand_size_max": B["hand_size_max"],
            "attacks_before_retire": B["attacks_before_retire"],
            "rank_base_multiplier": B["rank_base_multiplier"],
            "fatigue_turns": B["fatigue_turns"],
            "item_draw_per_turn": B["item_draw_per_turn"],
        },
        "monster": {
            "suit_rules": _monster_suit_rules(),
            "faces": group(monsters, FACE_RANKS),
            "numbers": group(monsters, NUMBER_RANKS),
            "demon": {
                "hp": d["hp"], "atk": d["atk"], "def": d["def"], "turns": d["turns"],
                "text": "♠A「魔王降臨」で登場。バトル場にいる間{}ターンで消滅（ベンチにいる間は数えない）、"
                        "魔王同士は攻撃できない".format(d["turns"]),
            },
        },
        "item": {
            "suit_rules": _item_suit_rules(),
            "faces": group(items, FACE_RANKS),
            "numbers": group(items, NUMBER_RANKS),
        },
    }
