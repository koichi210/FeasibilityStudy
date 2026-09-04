# -*- coding: utf-8 -*-
"""
カード定義。

トランプ52枚（ジョーカー無し）を、モンスターカード／アイテムカードに読み替える。
「スート＝役割」「数字＝強さ」という原案のルールをそのままコード化している。

  ♠ スペード … 高火力・ハイリスク
  ♥ ハート   … 回復・防御
  ♦ ダイヤ   … 攻撃
  ♣ クラブ   … 戦術

数値は balance.json 側に外出ししてあるので、調整はそちらで行う。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BALANCE_PATH = os.path.join(ROOT, "balance.json")


def load_balance() -> dict:
    with open(BALANCE_PATH, encoding="utf-8") as f:
        return json.load(f)


BALANCE = load_balance()

SUITS = ["S", "H", "D", "C"]
SUIT_MARK = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_NAME = {"S": "スペード", "H": "ハート", "D": "ダイヤ", "C": "クラブ"}
RANKS = list(range(2, 15))  # 2〜10, 11=J, 12=Q, 13=K, 14=A
FACE_LABEL = {11: "J", 12: "Q", 13: "K", 14: "A"}


def rank_label(rank: int) -> str:
    return FACE_LABEL.get(rank, str(rank))


# --------------------------------------------------------------------------
# モンスターの名前（数字カード 2〜10）
# --------------------------------------------------------------------------
MONSTER_NAMES: Dict[str, List[str]] = {
    "S": ["スケルトン", "インプ", "ガーゴイル", "ワイバーン", "デーモン",
          "リッチ", "ヘルハウンド", "バンシー", "ダークドラゴン"],
    "H": ["スライム", "フェアリー", "ヒーラー", "ユニコーン", "ペガサス",
          "セイレーン", "グリフォン", "ケンタウロス", "ホーリーバード"],
    "D": ["ゴブリン", "コボルト", "オーク", "ウルフ", "バーサーカー",
          "ミノタウロス", "サイクロプス", "タイタン", "ベヒーモス"],
    "C": ["マンドラゴラ", "ウィスプ", "ゴーレム", "トレント", "ワーム",
          "キメラ", "ナーガ", "スフィンクス", "ヒュドラ"],
}


@dataclass
class Ability:
    """モンスターの「技」。効果の実処理は game.py 側のフックが持つ。"""
    id: str
    name: str
    text: str


@dataclass
class ItemEffect:
    """アイテムの効果。type で game.py 側が処理を振り分ける。"""
    type: str
    value: int
    text: str
    extra: int = 0


@dataclass
class Card:
    suit: str
    rank: int
    kind: str  # "monster" | "item"
    name: str
    atk: int = 0
    dfn: int = 0
    ability: Optional[Ability] = None
    effect: Optional[ItemEffect] = None

    @property
    def code(self) -> str:
        return "{}{}".format(self.suit, rank_label(self.rank))

    @property
    def label(self) -> str:
        return "{}{}".format(SUIT_MARK[self.suit], rank_label(self.rank))

    def to_dict(self) -> dict:
        d = {
            "code": self.code,
            "label": self.label,
            "suit": self.suit,
            "mark": SUIT_MARK[self.suit],
            "rank": self.rank,
            "rank_label": rank_label(self.rank),
            "kind": self.kind,
            "name": self.name,
            "atk": self.atk,
            "dfn": self.dfn,
        }
        if self.ability:
            d["ability"] = {"id": self.ability.id, "name": self.ability.name,
                            "text": self.ability.text}
        if self.effect:
            d["effect"] = {"type": self.effect.type, "value": self.effect.value,
                           "text": self.effect.text}
        return d


# --------------------------------------------------------------------------
# 絵札・エースの特殊能力テーブル
#   ステータスは数字カードと同じ計算式（J=11, Q=12, K=13 を数字扱い）。
#   A だけは完全に個別設定。
# --------------------------------------------------------------------------
AV = BALANCE["ability_values"]

FACE_ABILITIES: Dict[str, Dict[str, str]] = {
    # --- J（11） ---
    "DJ": {"name": "デュアルブレイド", "id": "D_J_splash",
           "text": "攻撃時、相手のベンチ全体にも{}ダメージ".format(AV["D_J_splash"])},
    "HJ": {"name": "ヒーリングナイト", "id": "H_J_regen",
           "text": "自分のターン開始時、自分の場の全モンスターのHPを{}回復".format(AV["H_J_regen"])},
    "CJ": {"name": "トリックスター", "id": "C_J_disturb",
           "text": "攻撃時、相手のバトル場を疲労させる"},
    "SJ": {"name": "バーサークソード", "id": "S_J_reckless",
           "text": "攻撃時、ダメージ+{} / 自分に{}ダメージ".format(
               AV["S_J_reckless_bonus"], AV["S_J_reckless_recoil"])},
    # --- Q（12） ---
    "DQ": {"name": "ピアススピア", "id": "D_Q_pierce",
           "text": "攻撃時、相手の防御を{}%として計算".format(int(AV["D_Q_pierce_rate"] * 100))},
    "HQ": {"name": "聖女クイーン", "id": "H_Q_guard",
           "text": "ベンチにいる間、バトル場の防御+{}".format(AV["H_Q_guard"])},
    "CQ": {"name": "策謀のクイーン", "id": "C_Q_scheme",
           "text": "登場時、アイテムを{}枚引く".format(AV["C_Q_draw"])},
    "SQ": {"name": "ポイズンクイーン", "id": "S_Q_poison",
           "text": "攻撃時、相手に毒（毎ターン{}ダメージ）".format(AV["S_Q_poison"])},
    # --- K（13） ---
    "DK": {"name": "破壊王", "id": "D_K_destroyer",
           "text": "攻撃時、相手トレーナーにも{}ダメージ".format(AV["D_K_trainer_damage"])},
    "HK": {"name": "聖王", "id": "H_K_holy",
           "text": "登場時、自分のトレーナーHPを{}回復".format(AV["H_K_trainer_heal"])},
    "CK": {"name": "指揮官キング", "id": "C_K_command",
           "text": "ベンチにいる間、バトル場の攻撃+{}".format(AV["C_K_command"])},
    "SK": {"name": "暴君", "id": "S_K_tyrant",
           "text": "攻撃しても疲労しない / 攻撃のたび自分に{}ダメージ".format(
               AV["S_K_tyrant_recoil"])},
    # --- A（14） ---
    "DA": {"name": "一撃必殺", "id": "D_A_onehit",
           "text": "攻撃力{}。ただし1回攻撃したら即退場".format(AV["D_A_atk"])},
    "HA": {"name": "不死鳥", "id": "H_A_phoenix",
           "text": "倒されたとき、1度だけHP全快で復活する"},
    "CA": {"name": "賢者", "id": "C_A_sage",
           "text": "登場時、アイテムを手札上限まで補充する"},
    "SA": {"name": "魔王降臨", "id": "S_A_demon",
           "text": "登場時、魔王に変身（HP{} 攻{} 防{} / バトル場にいる間{}ターンで消滅・"
                   "ベンチにいる間はカウントされない・魔王同士は攻撃不可）".format(
               BALANCE["demon_lord"]["hp"], BALANCE["demon_lord"]["atk"],
               BALANCE["demon_lord"]["def"], BALANCE["demon_lord"]["turns"])},
}

# A のステータスだけ個別指定
ACE_STATS = {
    "D": (AV["D_A_atk"], AV["D_A_def"]),
    "H": (AV["H_A_atk"], AV["H_A_def"]),
    "C": (AV["C_A_atk"], AV["C_A_def"]),
    "S": (AV["S_A_atk"], AV["S_A_def"]),
}


def monster_stats(suit: str, rank: int) -> (int, int):
    """モンスターの攻撃力・防御力を算出する。"""
    if rank == 14:
        return ACE_STATS[suit]
    base = rank * BALANCE["rank_base_multiplier"]
    mod = BALANCE["suit_modifier"][suit]
    lo = BALANCE["stat_min"]
    return max(lo, base + mod["atk"]), max(lo, base + mod["def"])


def make_monster(suit: str, rank: int) -> Card:
    atk, dfn = monster_stats(suit, rank)
    key = suit + rank_label(rank)
    if key in FACE_ABILITIES:
        info = FACE_ABILITIES[key]
        name = info["name"]
        ability = Ability(info["id"], info["name"], info["text"])
    else:
        name = MONSTER_NAMES[suit][rank - 2]
        ability = None
    return Card(suit=suit, rank=rank, kind="monster", name=name,
                atk=atk, dfn=dfn, ability=ability)


def build_monster_deck() -> List[Card]:
    """モンスターデッキ（トランプ1箱＝52枚）を組む。"""
    return [make_monster(s, r) for s in SUITS for r in RANKS]


# --------------------------------------------------------------------------
# アイテムカード
# --------------------------------------------------------------------------
IV = BALANCE["item_values"]

ITEM_FACE: Dict[str, ItemEffect] = {
    # ♥ 回復
    "HJ": ItemEffect("heal", IV["H_J_heal"], "応急処置：バトル場のHPを{}回復".format(IV["H_J_heal"])),
    "HQ": ItemEffect("trainer_heal", IV["H_Q_trainer_heal"],
                     "女神の祝福：トレーナーHPを{}回復".format(IV["H_Q_trainer_heal"])),
    "HK": ItemEffect("full_heal", 0, "完全回復：バトル場のHPを全回復"),
    "HA": ItemEffect("revive", 0, "蘇生の秘薬：捨て札のモンスター1体をベンチに戻す"),
    # ♦ 武器
    "DJ": ItemEffect("weapon", IV["D_J_weapon"], "鋭い刃：攻撃+{}（装備）".format(IV["D_J_weapon"])),
    "DQ": ItemEffect("weapon_cursed", IV["D_Q_weapon"],
                     "魔剣：攻撃+{} / 毎ターン自分に{}ダメージ".format(IV["D_Q_weapon"], IV["D_Q_curse"]),
                     extra=IV["D_Q_curse"]),
    "DK": ItemEffect("weapon_fragile", IV["D_K_weapon"],
                     "伝説の剣：攻撃+{}。1回攻撃すると壊れる".format(IV["D_K_weapon"])),
    "DA": ItemEffect("burn", IV["D_A_burn"], "極大魔法：相手バトル場に{}ダメージ".format(IV["D_A_burn"])),
    # ♣ 戦術
    "CJ": ItemEffect("cure_fatigue", 0, "気付け薬：疲労を回復して今すぐ攻撃できる"),
    "CQ": ItemEffect("free_swap", 0, "入れ替え：交代権を消費せずに交代する"),
    "CK": ItemEffect("deploy", 0, "号令：デッキからベンチにモンスターを1体追加展開"),
    "CA": ItemEffect("draw_items", IV["C_A_draw"], "賢者の杖：アイテムを{}枚引く".format(IV["C_A_draw"])),
    # ♠ 禁断
    "SJ": ItemEffect("poison", IV["S_J_poison"],
                     "毒の刃：相手バトル場に毒（毎ターン{}ダメージ）".format(IV["S_J_poison"])),
    "SQ": ItemEffect("stun", 0, "呪縛：相手は次のターン攻撃できない"),
    "SK": ItemEffect("sacrifice", IV["S_K_sacrifice"],
                     "生贄の儀式：自分のバトル場を退場させ、相手トレーナーに{}ダメージ".format(
                         IV["S_K_sacrifice"])),
    "SA": ItemEffect("forbidden", IV["S_A_self_damage"],
                     "禁断の契約：自分のトレーナーHP-{} / 相手バトル場を即退場".format(
                         IV["S_A_self_damage"])),
}

ITEM_NUMBER_NAMES = {"H": "薬草", "D": "武器", "C": "防具", "S": "呪符"}


def make_item(suit: str, rank: int) -> Card:
    key = suit + rank_label(rank)
    if key in ITEM_FACE:
        eff = ITEM_FACE[key]
        name = eff.text.split("：")[0]
        return Card(suit=suit, rank=rank, kind="item", name=name, effect=eff)

    n = rank
    if suit == "H":
        v = n * IV["heal_per_rank"]
        eff = ItemEffect("heal", v, "薬草：バトル場のHPを{}回復".format(v))
    elif suit == "D":
        v = n * IV["weapon_per_rank"]
        eff = ItemEffect("weapon", v, "武器：攻撃+{}（装備）".format(v))
    elif suit == "C":
        v = n * IV["armor_per_rank"]
        eff = ItemEffect("armor", v, "防具：防御+{}（装備）".format(v))
    else:  # S
        v = n * IV["burn_per_rank"]
        rec = n * IV["burn_recoil_per_rank"]
        eff = ItemEffect("burn", v,
                         "呪符：相手バトル場に{}ダメージ / 自分にも{}ダメージ".format(v, rec),
                         extra=rec)
    return Card(suit=suit, rank=rank, kind="item",
                name="{}{}".format(ITEM_NUMBER_NAMES[suit], rank_label(rank)), effect=eff)


def build_item_deck() -> List[Card]:
    """アイテムデッキ（トランプ1箱＝52枚）を組む。PoCでは両者で共有する。"""
    return [make_item(s, r) for s in SUITS for r in RANKS]
