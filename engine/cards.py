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
    cry: str = ""   # 使用時に叫ぶ口上。ログに出る（演出専用、ルールには影響しない）


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
           "text": "自分のターン開始時、自分の場の全モンスターのHPを{}回復"
                   "（ベンチにいられるのは{}ターンまで）".format(
                       AV["H_J_regen"], BALANCE["bench_ability_turns"])},
    "CJ": {"name": "トリックスター", "id": "C_J_disturb",
           "text": "攻撃時、相手のバトル場を疲労させる"},
    "SJ": {"name": "バーサークソード", "id": "S_J_reckless",
           "text": "攻撃時、ダメージ+{} / 自分に{}ダメージ".format(
               AV["S_J_reckless_bonus"], AV["S_J_reckless_recoil"])},
    # --- Q（12） ---
    "DQ": {"name": "ピアススピア", "id": "D_Q_pierce",
           "text": "攻撃時、相手の防御を{}%として計算".format(int(AV["D_Q_pierce_rate"] * 100))},
    "HQ": {"name": "聖女クイーン", "id": "H_Q_guard",
           "text": "ベンチにいる間、バトル場の防御+{}（ベンチにいられるのは{}ターンまで）".format(
               AV["H_Q_guard"], BALANCE["bench_ability_turns"])},
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
           "text": "ベンチにいる間、バトル場の攻撃+{}（ベンチにいられるのは{}ターンまで）".format(
               AV["C_K_command"], BALANCE["bench_ability_turns"])},
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
    "HJ": ItemEffect("heal", IV["H_J_heal"], "応急処置：バトル場のHPを{}回復".format(IV["H_J_heal"]),
                     cry="まだ倒れるな、立ち上がれ！"),
    "HQ": ItemEffect("trainer_heal", IV["H_Q_trainer_heal"],
                     "女神の祝福：トレーナーHPを{}回復".format(IV["H_Q_trainer_heal"]),
                     cry="女神よ、我にその加護を！"),
    "HK": ItemEffect("full_heal", 0, "完全回復：バトル場のHPを全回復",
                     cry="甦れ、我が魂の器よ！"),
    "HA": ItemEffect("revive", 0, "蘇生の秘薬：捨て札のモンスター1体をベンチに戻す",
                     cry="死者の眠りを破れ、いま一度この地に還れ！"),
    # ♦ 武器
    "DJ": ItemEffect("weapon", IV["D_J_weapon"], "鋭い刃：攻撃+{}（装備）".format(IV["D_J_weapon"]),
                     cry="研ぎ澄まされし刃よ、我が手に来たれ！"),
    "DQ": ItemEffect("weapon_cursed", IV["D_Q_weapon"],
                     "魔剣：攻撃+{} / 毎ターン自分に{}ダメージ".format(IV["D_Q_weapon"], IV["D_Q_curse"]),
                     extra=IV["D_Q_curse"],
                     cry="我が血を喰らえ、呪われし魔剣よ！"),
    "DK": ItemEffect("weapon_fragile", IV["D_K_weapon"],
                     "伝説の剣：攻撃+{}。1回攻撃すると壊れる".format(IV["D_K_weapon"]),
                     cry="伝説よ、いま一度この手に宿れ！"),
    "DA": ItemEffect("burn", IV["D_A_burn"], "極大魔法：相手バトル場に{}ダメージ".format(IV["D_A_burn"]),
                     cry="灰も残さず消え去れ、極大消滅呪文！"),
    # ♣ 戦術
    "CJ": ItemEffect("cure_fatigue", 0, "気付け薬：疲労を回復して今すぐ攻撃できる",
                     cry="目を覚ませ、戦いはこれからだ！"),
    "CQ": ItemEffect("free_swap", 0, "入れ替え：交代権を消費せずに交代する",
                     cry="陣を組み替えよ、疾く走れ！"),
    "CK": ItemEffect("deploy", 0, "号令：デッキからベンチにモンスターを1体追加展開",
                     cry="集え、我が眷属たちよ！"),
    "CA": ItemEffect("draw_items", IV["C_A_draw"], "賢者の杖：アイテムを{}枚引く".format(IV["C_A_draw"]),
                     cry="叡智よ、我に至る道を示せ！"),
    # ♠ 禁断
    "SJ": ItemEffect("poison", IV["S_J_poison"],
                     "毒の刃：相手バトル場に毒（毎ターン{}ダメージ）".format(IV["S_J_poison"]),
                     cry="蝕め、蒼き猛毒よ！"),
    "SQ": ItemEffect("stun", 0, "呪縛：相手は次のターン攻撃できない",
                     cry="動くな、闇の鎖に囚われよ！"),
    "SK": ItemEffect("sacrifice", IV["S_K_sacrifice"],
                     "生贄の儀式：自分のバトル場を退場させ、相手トレーナーに{}ダメージ".format(
                         IV["S_K_sacrifice"]),
                     cry="その命、我が勝利の糧となれ！"),
    "SA": ItemEffect("forbidden", IV["S_A_self_damage"],
                     "禁断の契約：自分のトレーナーHP-{} / 相手バトル場を即退場".format(
                         IV["S_A_self_damage"]),
                     cry="代償は我が魂、禁忌の扉よ開け！"),
}

# 数字カード（2〜10）の名前。数字が上がるほど大仰になるように並べてある。
# 効果はスートごとに固定（♥回復 / ♦武器 / ♣防具 / ♠呪符）で、
# 数字が強さなので、名前もその順で格を上げていく。
ITEM_NUMBER_NAMES: Dict[str, List[str]] = {
    "H": ["蒼天の雫", "翠玉の霊薬", "月光の癒歌", "聖泉のしずく", "白銀の秘薬",
          "生命樹の雫", "星霜の霊薬", "天恵の聖水", "楽園の甘露"],
    "D": ["鉄爪の刃", "蒼焔の短剣", "双牙の剣", "疾風の刃", "猛火の戦斧",
          "雷鳴の長剣", "竜牙の大剣", "業火の魔刀", "天穿つ聖剣"],
    "C": ["鉄壁の胸当て", "樫盾の加護", "蒼鋼の鎧", "不動の城壁", "精霊銀の鎧",
          "龍鱗の護り", "神鉄の大盾", "絶対障壁", "天上の聖鎧"],
    "S": ["灼熱の呪符", "黒炎の呪印", "破滅の呪符", "冥界の呪詛", "煉獄の焔符",
          "深淵の呪印", "滅魔の呪符", "終焉の呪言", "天罰の裁き符"],
}

# 数字カードの口上。名前を差し込んで叫ぶ。
ITEM_NUMBER_CRIES = {
    "H": "{}よ、我が同胞を癒せ！",
    "D": "{}よ、我が敵を斬り裂け！",
    "C": "{}よ、我が身を守り抜け！",
    "S": "{}よ、彼の者に災いあれ！",
}


def make_item(suit: str, rank: int) -> Card:
    key = suit + rank_label(rank)
    if key in ITEM_FACE:
        eff = ITEM_FACE[key]
        name = eff.text.split("：")[0]
        return Card(suit=suit, rank=rank, kind="item", name=name, effect=eff)

    n = rank
    name = ITEM_NUMBER_NAMES[suit][rank - 2]
    cry = ITEM_NUMBER_CRIES[suit].format(name)
    if suit == "H":
        v = n * IV["heal_per_rank"]
        eff = ItemEffect("heal", v, "{}：バトル場のHPを{}回復".format(name, v), cry=cry)
    elif suit == "D":
        v = n * IV["weapon_per_rank"]
        eff = ItemEffect("weapon", v, "{}：攻撃+{}（装備）".format(name, v), cry=cry)
    elif suit == "C":
        v = n * IV["armor_per_rank"]
        eff = ItemEffect("armor", v, "{}：防御+{}（装備）".format(name, v), cry=cry)
    else:  # S
        v = n * IV["burn_per_rank"]
        rec = n * IV["burn_recoil_per_rank"]
        eff = ItemEffect("burn", v,
                         "{}：相手バトル場に{}ダメージ / 自分にも{}ダメージ".format(name, v, rec),
                         extra=rec, cry=cry)
    return Card(suit=suit, rank=rank, kind="item", name=name, effect=eff)


def build_item_deck() -> List[Card]:
    """アイテムデッキ（トランプ1箱＝52枚）を組む。PoCでは両者で共有する。"""
    return [make_item(s, r) for s in SUITS for r in RANKS]
