# -*- coding: utf-8 -*-
"""
カード定義。

トランプ52枚（ジョーカー無し）を、エネミーカード／アイテムカードに読み替える。
「スート＝役割」「数字＝強さ」という原案のルールをそのままコード化している。

  ♠ スペード … 高火力・ハイリスク
  ♥ ハート   … 回復・防御
  ♦ ダイヤ   … 攻撃
  ♣ クラブ   … 戦術

数値は balance.json 側に外出ししてあるので、調整はそちらで行う。

--------------------------------------------------------------------------
スキンについて
--------------------------------------------------------------------------
カードの「名前」（エネミー名・技名・キャラ名・アイテム名・叫び口上）は
`skins/*.json` から読み込む。デフォルトは `skins/arcana.json`。

サーバー起動時は `skin_config.json`（engine/skins.py が読む）に保存された
スキンで初期化される。⚙️オプション画面からスキンを選んだときは、
`apply_skin(skin_id)` を呼ぶことでモジュール内の辞書をその場で書き換える
（＝サーバー再起動なしで次の対戦から反映される。server/app.py の /api/skin 参照）。
balance.json を手で直接編集したときだけ、今まで通りサーバー再起動が必要。

技のid・ダメージ計算式・発動条件などのルール本体はスキンに関係なく
ここに書かれた共通コードが担当する。スキンが変えられるのは見た目の名前と、
ごく一部の数値（`balance_overrides`。例：転スラスキンの魔王リムル「多重展開」）だけ。

--------------------------------------------------------------------------
ホットリロードの実装メモ
--------------------------------------------------------------------------
game.py・ai.py・reference.py などが `from .cards import BALANCE` のように
辞書オブジェクトそのものを掴んでいる。apply_skin() で BALANCE を新しい辞書に
「差し替える」と、掴んでいる側には反映されない（名前の再束縛はコピー先には
伝わらないため）。そこで、BALANCE をはじめとする辞書・リストは最初に作った
オブジェクトを使い回し、中身だけを `clear()` + `update()` や
`skins.deep_update_inplace()` でその場で書き換える。関数（make_enemy 等）は
呼ばれるたびにモジュール変数を読みに行くので、この方式だけで辻褄が合う。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import skins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BALANCE_PATH = os.path.join(ROOT, "balance.json")


def load_balance() -> dict:
    with open(BALANCE_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


SUITS = ["S", "H", "D", "C"]
SUIT_MARK = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_NAME = {"S": "スペード", "H": "ハート", "D": "ダイヤ", "C": "クラブ"}
RANKS = list(range(2, 15))  # 2〜10, 11=J, 12=Q, 13=K, 14=A
FACE_LABEL = {11: "J", 12: "Q", 13: "K", 14: "A"}


def rank_label(rank: int) -> str:
    return FACE_LABEL.get(rank, str(rank))


@dataclass
class Ability:
    """エネミーの「技」。効果の実処理は game.py 側のフックが持つ。"""
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
    kind: str  # "enemy" | "item"
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
# スキン・数値まわりの「入れ物」。
# 中身は apply_skin() が書き換える。オブジェクト自体は起動時に一度だけ作って
# 使い回す（他モジュールが掴んでいる参照を生かしたままホットリロードするため）。
# --------------------------------------------------------------------------
SKIN_ID: str = ""
SKIN: dict = {}
BALANCE: dict = {}

ENEMY_NAMES: Dict[str, List[str]] = {}          # エネミーの名前（数字カード 2〜10）
FAN: Dict[str, str] = {}                        # 技名（表示名）
FACE_ABILITIES: Dict[str, Dict[str, str]] = {}  # 絵札・エースの特殊能力テーブル
FACE_ENEMY_NAMES: Dict[str, str] = {}           # 絵札エネミーの「カードに表示される名前」
ACE_STATS: Dict[str, tuple] = {}                # A のステータス（個別指定）

GOD_ARMY_KEYS = ["SJ", "SQ", "SK", "HJ", "HQ", "HK", "DJ", "DQ", "DK"]
GOD_ARMY_NAMES: Dict[str, str] = {}
DIVINE_ARMY_GROUP_NAME: str = "神々"

DEMON_ARMY_KEYS = ["S10", "S9", "S8", "D10", "D9", "D8"]
# どのJ/Q/Kの技を借りるか（同じスートの中で、10→J、9→Q、8→Kに対応させてある）
DEMON_ARMY_ABILITY_SOURCE: Dict[str, str] = {
    "S10": "SJ", "S9": "SQ", "S8": "SK",
    "D10": "DJ", "D9": "DQ", "D8": "DK",
}
DEMON_ARMY_NAMES: Dict[str, str] = {}
DEMON_ARMY_GROUP_NAME: str = "魔神"

IFN: Dict[str, str] = {}   # アイテム名（絵札）
IFC: Dict[str, str] = {}   # 叫び口上（絵札）
ITEM_FACE: Dict[str, ItemEffect] = {}
ITEM_NUMBER_NAMES: Dict[str, List[str]] = {}   # アイテム名（数字カード 2〜10）
ITEM_NUMBER_CRIES: Dict[str, str] = {}         # 数字カードの口上（{}に名前を差し込む）


def _sa_text() -> str:
    d = BALANCE["demon_lord"]
    text = ("登場時、魔王に変身（HP{} 攻{} 防{} / バトル場にいる間{}ターンで消滅・"
            "ベンチにいる間はカウントされない・魔王同士は攻撃不可）").format(
        d["hp"], d["atk"], d["def"], d["turns"])
    splash = d.get("splash", 0)
    if splash > 0:
        text += "。覚醒後は攻撃時に多重展開（マルチプル）：相手ベンチ全体にも{}ダメージ".format(splash)
    return text


def apply_skin(skin_id: str = None) -> None:
    """スキン（＋そのbalance_overrides）を読み込み直し、モジュール内の辞書をその場で書き換える。

    skin_id を省略すると `skin_config.json` に保存されている現在のスキンを読む。
    ⚙️オプション画面からの切り替えはサーバー起動中にこの関数を呼ぶだけで完結する
    （辞書オブジェクト自体は差し替えないので、他モジュールが `from .cards import BALANCE`
    のように掴んでいる参照にもそのまま反映される）。
    """
    global SKIN_ID, DIVINE_ARMY_GROUP_NAME, DEMON_ARMY_GROUP_NAME

    if skin_id is None:
        skin_id = skins.current_skin_id()
    new_skin = skins.load_skin(skin_id)
    new_balance = skins.merge_balance(load_balance(), new_skin)

    SKIN_ID = new_skin.get("id", skin_id)
    SKIN.clear()
    SKIN.update(new_skin)
    skins.deep_update_inplace(BALANCE, new_balance)

    AV = BALANCE["ability_values"]
    IV = BALANCE["item_values"]

    ENEMY_NAMES.clear()
    ENEMY_NAMES.update(SKIN["enemy_names"])

    FAN.clear()
    FAN.update(SKIN["face_ability_names"])

    # --- 絵札・エースの特殊能力テーブル ---------------------------------
    #   ステータスは数字カードと同じ計算式（J=11, Q=12, K=13 を数字扱い）。
    #   A だけは完全に個別設定。
    #   技のid・ルール文（数値の埋め込み計算式）はスキンに関係ない共通ルールなので
    #   ここでコード化する。技名（表示名）だけ SKIN["face_ability_names"] から取る。
    FACE_ABILITIES.clear()
    FACE_ABILITIES.update({
        # --- J（11） ---
        "DJ": {"name": FAN["DJ"], "id": "D_J_splash",
               "text": "攻撃時、相手のベンチ全体にも{}ダメージ".format(AV["D_J_splash"])},
        "HJ": {"name": FAN["HJ"], "id": "H_J_regen",
               "text": "自分のターン開始時、自分の場の全エネミーのHPを{}回復"
                       "（ベンチにいられるのは{}ターンまで）".format(
                           AV["H_J_regen"], BALANCE["bench_ability_turns"])},
        "CJ": {"name": FAN["CJ"], "id": "C_J_disturb",
               "text": "攻撃時、相手のバトル場を疲労させる"},
        "SJ": {"name": FAN["SJ"], "id": "S_J_reckless",
               "text": "攻撃時、ダメージ+{} / 自分に{}ダメージ".format(
                   AV["S_J_reckless_bonus"], AV["S_J_reckless_recoil"])},
        # --- Q（12） ---
        "DQ": {"name": FAN["DQ"], "id": "D_Q_pierce",
               "text": "攻撃時、相手の防御を{}%として計算".format(int(AV["D_Q_pierce_rate"] * 100))},
        "HQ": {"name": FAN["HQ"], "id": "H_Q_guard",
               "text": "ベンチにいる間、バトル場の防御+{}（ベンチにいられるのは{}ターンまで）".format(
                   AV["H_Q_guard"], BALANCE["bench_ability_turns"])},
        "CQ": {"name": FAN["CQ"], "id": "C_Q_scheme",
               "text": "登場時、アイテムを{}枚引く".format(AV["C_Q_draw"])},
        "SQ": {"name": FAN["SQ"], "id": "S_Q_poison",
               "text": "攻撃時、相手に毒（毎ターン{}ダメージ）".format(AV["S_Q_poison"])},
        # --- K（13） ---
        "DK": {"name": FAN["DK"], "id": "D_K_destroyer",
               "text": "攻撃時、相手トレーナーにも{}ダメージ".format(AV["D_K_trainer_damage"])},
        "HK": {"name": FAN["HK"], "id": "H_K_holy",
               "text": "登場時、自分のトレーナーHPを{}回復".format(AV["H_K_trainer_heal"])},
        "CK": {"name": FAN["CK"], "id": "C_K_command",
               "text": "ベンチにいる間、バトル場の攻撃+{}（ベンチにいられるのは{}ターンまで）".format(
                   AV["C_K_command"], BALANCE["bench_ability_turns"])},
        "SK": {"name": FAN["SK"], "id": "S_K_tyrant",
               "text": "攻撃しても疲労しない / 攻撃のたび自分に{}ダメージ".format(
                   AV["S_K_tyrant_recoil"])},
        # --- A（14） ---
        "DA": {"name": FAN["DA"], "id": "D_A_onehit",
               "text": "攻撃力{}。ただし1回攻撃したら即退場".format(AV["D_A_atk"])},
        "HA": {"name": FAN["HA"], "id": "H_A_phoenix",
               "text": "倒されたとき、1度だけHP全快で復活する"},
        "CA": {"name": FAN["CA"], "id": "C_A_sage",
               "text": "登場時、アイテムを手札上限まで補充する"},
        "SA": {"name": FAN["SA"], "id": "S_A_demon", "text": _sa_text()},
    })

    # 絵札エネミーの「カードに表示される名前」。
    # 技名（FACE_ABILITIES の name）はそのまま残し、見た目の名前だけを差し替えたい
    # スキン（例：転スラ）向け。キーが無ければ技名がそのまま表示名になる。
    FACE_ENEMY_NAMES.clear()
    FACE_ENEMY_NAMES.update(SKIN.get("face_enemy_names", {}))

    # A のステータスだけ個別指定
    ACE_STATS.clear()
    ACE_STATS.update({
        "D": (AV["D_A_atk"], AV["D_A_def"]),
        "H": (AV["H_A_atk"], AV["H_A_def"]),
        "C": (AV["C_A_atk"], AV["C_A_def"]),
        "S": (AV["S_A_atk"], AV["S_A_def"]),
    })

    # --- 神軍降臨：♠♥♦のJ/Q/K（クラブは対象外）の上位互換エネミー ------
    GOD_ARMY_NAMES.clear()
    GOD_ARMY_NAMES.update(SKIN["god_army_names"])
    DIVINE_ARMY_GROUP_NAME = SKIN.get("divine_army_group_name", "神々")

    # --- 魔神軍降臨：♠♦の10/9/8（ハート・クラブは対象外）の上位互換エネミー ---
    DEMON_ARMY_NAMES.clear()
    DEMON_ARMY_NAMES.update(SKIN["demon_army_names"])
    DEMON_ARMY_GROUP_NAME = SKIN.get("demon_army_group_name", "魔神")

    # --- アイテムカード ---------------------------------------------------
    # 技名と同じく、アイテムの「名前」「叫び口上」だけスキンから取る。
    # 効果の種類（type）・数値・ルール文の組み立ては共通コード側。
    IFN.clear()
    IFN.update(SKIN["item_face_names"])
    IFC.clear()
    IFC.update(SKIN["item_face_cries"])

    # ♣K「号令」は「神軍降臨」効果に差し替えてある（出現率を上げるため）。
    # 神軍降臨で召喚された上位互換エネミーは装備アイテムを使えない（共通ルール）。
    divine_army_text = (
        "{name}：自分のトレーナーHPが{trigger}以下のとき使用可。代償として自分のトレーナーHP-{cost}。"
        "ベンチを一新し、J・Q・K の上位互換の{group}を3体ランダム召喚する"
        "（元のベンチのエネミーは失われず、エネミー手札に戻る）。"
        "召喚された{group}は装備アイテム（武器・防具系のバフ）を使えない"
    ).format(name=IFN["CK"], trigger=BALANCE["divine_army"]["trigger_hp"],
             cost=BALANCE["divine_army"]["cost_hp"], group=DIVINE_ARMY_GROUP_NAME)

    # ♠A「禁断の契約」は「魔神軍降臨」効果に差し替えてある。
    # 神軍降臨と違い相手トレーナーHPの条件はなく、いつでも使える禁忌の一手。
    demon_army_text = (
        "{name}：いつでも使用可。代償として自分のトレーナーHP-{cost}。"
        "ベンチを一新し、♠♦の10・9・8 の上位互換の{group}を3体ランダム召喚する"
        "（元のベンチのエネミーは失われず、エネミー手札に戻る）"
    ).format(name=IFN["SA"], cost=BALANCE["demon_army"]["cost_hp"], group=DEMON_ARMY_GROUP_NAME)

    ITEM_FACE.clear()
    ITEM_FACE.update({
        # ♥ 回復
        "HJ": ItemEffect("heal", IV["H_J_heal"],
                         "{}：バトル場のHPを{}回復".format(IFN["HJ"], IV["H_J_heal"]), cry=IFC["HJ"]),
        "HQ": ItemEffect("trainer_heal", IV["H_Q_trainer_heal"],
                         "{}：トレーナーHPを{}回復".format(IFN["HQ"], IV["H_Q_trainer_heal"]), cry=IFC["HQ"]),
        "HK": ItemEffect("full_heal", 0, "{}：バトル場のHPを全回復".format(IFN["HK"]), cry=IFC["HK"]),
        "HA": ItemEffect("revive", 0,
                         "{}：捨て札のエネミー1体をエネミー手札に戻す".format(IFN["HA"]), cry=IFC["HA"]),
        # ♦ 武器
        "DJ": ItemEffect("weapon", IV["D_J_weapon"],
                         "{}：攻撃+{}（装備）".format(IFN["DJ"], IV["D_J_weapon"]), cry=IFC["DJ"]),
        "DQ": ItemEffect("weapon_cursed", IV["D_Q_weapon"],
                         "{}：攻撃+{} / 毎ターン自分に{}ダメージ".format(
                             IFN["DQ"], IV["D_Q_weapon"], IV["D_Q_curse"]),
                         extra=IV["D_Q_curse"], cry=IFC["DQ"]),
        "DK": ItemEffect("weapon_fragile", IV["D_K_weapon"],
                         "{}：攻撃+{}。1回攻撃すると壊れる".format(IFN["DK"], IV["D_K_weapon"]), cry=IFC["DK"]),
        "DA": ItemEffect("burn", IV["D_A_burn"],
                         "{}：相手バトル場に{}ダメージ".format(IFN["DA"], IV["D_A_burn"]), cry=IFC["DA"]),
        # ♣ 戦術
        "CJ": ItemEffect("cure_fatigue", 0,
                         "{}：疲労を回復して今すぐ攻撃できる".format(IFN["CJ"]), cry=IFC["CJ"]),
        "CQ": ItemEffect("free_swap", 0,
                         "{}：交代権を消費せずに交代する".format(IFN["CQ"]), cry=IFC["CQ"]),
        "CK": ItemEffect("divine_army", 0, divine_army_text, cry=IFC["CK"]),
        "CA": ItemEffect("draw_items", IV["C_A_draw"],
                         "{}：アイテムを{}枚引く".format(IFN["CA"], IV["C_A_draw"]), cry=IFC["CA"]),
        # ♠ 禁断
        "SJ": ItemEffect("poison", IV["S_J_poison"],
                         "{}：相手バトル場に毒（毎ターン{}ダメージ）".format(IFN["SJ"], IV["S_J_poison"]),
                         cry=IFC["SJ"]),
        "SQ": ItemEffect("stun", 0,
                         "{}：相手は次のターン攻撃できない".format(IFN["SQ"]), cry=IFC["SQ"]),
        "SK": ItemEffect("sacrifice", IV["S_K_sacrifice"],
                         "{}：自分のバトル場を退場させ、相手トレーナーに{}ダメージ".format(
                             IFN["SK"], IV["S_K_sacrifice"]), cry=IFC["SK"]),
        "SA": ItemEffect("demon_army", 0, demon_army_text, cry=IFC["SA"]),
    })

    # 数字カード（2〜10）の名前。数字が上がるほど大仰になるように並べてある。
    # 効果はスートごとに固定（♥回復 / ♦武器 / ♣防具 / ♠呪符）で、
    # 数字が強さなので、名前もその順で格を上げていく。
    ITEM_NUMBER_NAMES.clear()
    ITEM_NUMBER_NAMES.update(SKIN["item_number_names"])
    # 数字カードの口上。名前を差し込んで叫ぶ。
    ITEM_NUMBER_CRIES.clear()
    ITEM_NUMBER_CRIES.update(SKIN["item_number_cries"])


apply_skin()


def enemy_stats(suit: str, rank: int) -> (int, int):
    """エネミーの攻撃力・防御力を算出する。"""
    if rank == 14:
        return ACE_STATS[suit]
    base = rank * BALANCE["rank_base_multiplier"]
    mod = BALANCE["suit_modifier"][suit]
    lo = BALANCE["stat_min"]
    return max(lo, base + mod["atk"]), max(lo, base + mod["def"])


def make_enemy(suit: str, rank: int) -> Card:
    atk, dfn = enemy_stats(suit, rank)
    key = suit + rank_label(rank)
    if key in FACE_ABILITIES:
        info = FACE_ABILITIES[key]
        name = FACE_ENEMY_NAMES.get(key, info["name"])
        ability = Ability(info["id"], info["name"], info["text"])
    else:
        name = ENEMY_NAMES[suit][rank - 2]
        ability = None
    return Card(suit=suit, rank=rank, kind="enemy", name=name,
                atk=atk, dfn=dfn, ability=ability)


def build_enemy_deck() -> List[Card]:
    """エネミーデッキ（トランプ1箱＝52枚）を組む。"""
    return [make_enemy(s, r) for s in SUITS for r in RANKS]


def make_god_enemy(key: str) -> Card:
    """神軍降臨で召喚される、J/Q/Kの上位互換エネミーを1体作る。

    key は "SJ"/"SQ"/"SK"/"HJ"/"HQ"/"HK"/"DJ"/"DQ"/"DK" のいずれか。
    """
    suit, rank = key[0], {"J": 11, "Q": 12, "K": 13}[key[1]]
    atk, dfn = enemy_stats(suit, rank)
    dv = BALANCE["divine_army"]
    atk += dv["atk_bonus"]
    dfn += dv["def_bonus"]
    base = FACE_ABILITIES[key]
    ability = Ability(base["id"], base["name"], base["text"])
    return Card(suit=suit, rank=rank, kind="enemy", name=GOD_ARMY_NAMES[key],
                atk=atk, dfn=dfn, ability=ability)


def make_demon_enemy(key: str) -> Card:
    """魔神軍降臨で召喚される、10/9/8の上位互換エネミーを1体作る。

    key は "S10"/"S9"/"S8"/"D10"/"D9"/"D8" のいずれか。
    """
    suit, rank = key[0], int(key[1:])
    atk, dfn = enemy_stats(suit, rank)
    da = BALANCE["demon_army"]
    atk += da["atk_bonus"]
    dfn += da["def_bonus"]
    base = FACE_ABILITIES[DEMON_ARMY_ABILITY_SOURCE[key]]
    ability = Ability(base["id"], base["name"], base["text"])
    return Card(suit=suit, rank=rank, kind="enemy", name=DEMON_ARMY_NAMES[key],
                atk=atk, dfn=dfn, ability=ability)


def make_item(suit: str, rank: int) -> Card:
    key = suit + rank_label(rank)
    if key in ITEM_FACE:
        eff = ITEM_FACE[key]
        name = eff.text.split("：")[0]
        return Card(suit=suit, rank=rank, kind="item", name=name, effect=eff)

    n = rank
    iv = BALANCE["item_values"]
    name = ITEM_NUMBER_NAMES[suit][rank - 2]
    cry = ITEM_NUMBER_CRIES[suit].format(name)
    if suit == "H":
        v = n * iv["heal_per_rank"]
        eff = ItemEffect("heal", v, "{}：バトル場のHPを{}回復".format(name, v), cry=cry)
    elif suit == "D":
        v = n * iv["weapon_per_rank"]
        eff = ItemEffect("weapon", v, "{}：攻撃+{}（装備）".format(name, v), cry=cry)
    elif suit == "C":
        v = n * iv["armor_per_rank"]
        eff = ItemEffect("armor", v, "{}：防御+{}（装備）".format(name, v), cry=cry)
    else:  # S
        v = n * iv["burn_per_rank"]
        rec = n * iv["burn_recoil_per_rank"]
        eff = ItemEffect("burn", v,
                         "{}：相手バトル場に{}ダメージ / 自分にも{}ダメージ".format(name, v, rec),
                         extra=rec, cry=cry)
    return Card(suit=suit, rank=rank, kind="item", name=name, effect=eff)


def build_item_deck() -> List[Card]:
    """アイテムデッキ（トランプ1箱＝52枚）を組む。PoCでは両者で共有する。"""
    return [make_item(s, r) for s in SUITS for r in RANKS]
