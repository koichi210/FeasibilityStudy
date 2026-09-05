# -*- coding: utf-8 -*-
"""
CPU プレイヤー。

ルールを理解しているだけの素直な思考ルーチン。
「まず有利なアイテムを使い、必要なら交代し、殴れるなら殴る」だけ。
強さは3段階（初級／中級／上級）を balance.json の ai_levels で切り替える。
  - 初級：一定確率でわざと適当な手を選ぶ（mistake_rate）
  - 中級：これまでの挙動そのまま（数値は変更なし）
  - 上級：今すぐ倒し切れるなら最優先で攻撃し、アイテムも積極的に使う
強さの調整はここと balance.json だけで済むように、Game からは独立させてある。
"""
from __future__ import annotations

from typing import List, Optional

from .cards import BALANCE
from .game import Game, Player

B = BALANCE
AV = B["ability_values"]
AI_LEVELS = B["ai_levels"]

CPU_LEVELS = ("easy", "normal", "hard")
DEFAULT_CPU_LEVEL = "normal"
CPU_LEVEL_LABELS = {
    "easy": "🐣 初級",
    "normal": "⚔️ 中級",
    "hard": "🔥 上級",
}


def _level_conf(level: str) -> dict:
    """強さ名から balance.json の設定を取り出す。知らない名前は中級扱い。"""
    return AI_LEVELS.get(level) or AI_LEVELS[DEFAULT_CPU_LEVEL]


def _score_item(g: Game, p: Player, o: Player, card, conf: dict) -> float:
    """そのアイテムを今使う価値をざっくり点数化する。"""
    e = card.effect
    t, v = e.type, e.value
    bm, om = p.battle, o.battle
    hp_rate = (bm.hp / bm.hp_max) if bm else 1.0

    if t in ("heal", "full_heal"):
        if not bm or hp_rate > conf["heal_hp_threshold"]:
            return -1
        missing = bm.hp_max - bm.hp
        gain = missing if t == "full_heal" else min(v, missing)
        return gain * 1.0
    if t == "trainer_heal":
        return v * 0.8 if p.trainer_hp < p.trainer_hp_max * 0.6 else -1
    if t in ("weapon", "weapon_fragile"):
        # 攻撃直前に付けたい。疲労中なら価値が下がる
        if not bm or not bm.can_attack:
            return -1
        return v * 1.2
    if t == "weapon_cursed":
        if not bm or not bm.can_attack:
            return -1
        return v * 1.0 - e.extra * 2
    if t == "armor":
        return v * 0.6 if bm else -1
    if t == "burn":
        if not om:
            return -1
        lethal = 30 if om.hp <= v else 0
        return v * 1.1 + lethal - e.extra * 0.5
    if t == "poison":
        return v * 1.5 if om and om.hp > v else -1
    if t == "stun":
        return 35 if om and om.can_attack else -1
    if t == "cure_fatigue":
        return 40 if bm and bm.fatigue > 0 else -1
    if t == "free_swap":
        return 5
    if t == "deploy":
        return 15 if len(p.monster_hand) < B["monster_hand_size_max"] else -1
    if t == "draw_items":
        return 20
    if t == "revive":
        return 25 if len(p.monster_hand) < B["monster_hand_size_max"] else -1
    if t == "sacrifice":
        # 瀕死のモンスターを捧げるのは有効
        return (v + 20) if bm and hp_rate < 0.3 else -1
    if t == "forbidden":
        # 相手の主力を消せるなら
        if not om:
            return -1
        threat = om.base_atk + om.atk_bonus
        return threat - v
    return 0


def _hand_power(p: Player, i: int) -> int:
    """モンスター手札のi番目の強さ（配置の優先度づけに使うだけ）。"""
    c = p.monster_hand[i]
    return c.atk + c.dfn


def _bench_power(p: Player, i: int) -> int:
    """ベンチのi番目の頼もしさ（バトル場へ繰り上げる相手を選ぶのに使う）。"""
    m = p.bench[i] if 0 <= i < len(p.bench) else None
    return (m.hp + m.base_atk) if m else -1


def _can_finish_now(p: Player, o: Player) -> bool:
    """いま攻撃すれば、相手トレーナーを直接攻撃で倒し切れるかどうか（簡易判定）。

    上級CPU専用。ベンチの号令(C_K_command)と無謀の型(S_J_reckless)くらいの
    ボーナスだけ見ていて、game.py の _do_attack ほど厳密ではない。
    見逃しはあっても実害はない（次のチャンスにまた判定される）ので、これで十分。
    """
    if not (p.battle and not p.attacked and p.battle.can_attack):
        return False
    if p.battle.is_demon and o.battle and o.battle.is_demon:
        return False
    if o.battle is not None:
        return False  # 相手の場にモンスターがいる間は直接攻撃にならない
    atk = p.battle.base_atk + p.battle.atk_bonus
    if p.has_bench_ability("C_K_command"):
        atk += AV["C_K_command"]
    if p.battle.ability_id == "S_J_reckless":
        atk += AV["S_J_reckless_bonus"]
    return o.trainer_hp <= atk


def choose_action(g: Game, level: str = DEFAULT_CPU_LEVEL) -> dict:
    """CPU の1手を返す。"""
    conf = _level_conf(level)
    p = g.players[g.current]
    o = g.players[1 - g.current]
    actions = g.legal_actions()
    if not actions:
        return {"type": "end_turn"}

    # 初級はときどきわざと適当な手を選ぶ（弱くする）
    mistake_rate = conf.get("mistake_rate", 0.0)
    if mistake_rate and g.rng.random() < mistake_rate:
        return g.rng.choice(actions)

    by_type = {}
    for a in actions:
        by_type.setdefault(a["type"], []).append(a)

    # 選択待ちのときは、それしかできない。まず片付ける。
    # （CPU は engine 側で自動的に選ぶので普段ここへは来ないが、
    #   来たときに手が無くて固まると進行が止まるので保険として残す）
    if "pick" in by_type:
        return by_type["pick"][0]
    if "promote" in by_type:
        return max(by_type["promote"],
                   key=lambda a: _bench_power(p, a["bench"]))

    # 0) モンスターの配置：置かないと何も始まらないので最優先。
    #    バトル場が空いているならまずそこへ、一番強いものを出す。
    if "place" in by_type:
        battle_places = [a for a in by_type["place"] if a["slot"] == "battle"]
        pool = battle_places or by_type["place"]
        return max(pool, key=lambda a: _hand_power(p, a["hand"]))

    # 0.5) 上級は、今すぐ倒し切れるならそれを最優先する
    if conf.get("lethal_priority") and "attack" in by_type and _can_finish_now(p, o):
        return by_type["attack"][0]

    # 1) アイテム：一番点数の高いものが十分な価値ならそれを使う
    if "item" in by_type:
        best, best_score = None, 0.0
        for a in by_type["item"]:
            card = p.hand[a["hand"]]
            s = _score_item(g, p, o, card, conf)
            if s > best_score:
                best, best_score = a, s
        if best and best_score >= conf["item_threshold"]:
            return best

    # 2) 交代：バトル場が瀕死 or 疲労中で、ベンチに動けるやつがいるなら替える
    if "swap" in by_type and p.battle:
        hp_rate = p.battle.hp / p.battle.hp_max
        stuck = p.battle.fatigue > 0
        weak = hp_rate <= conf["swap_hp_threshold"]
        if (stuck or weak) and not p.battle.is_demon:
            fresh = [a for a in by_type["swap"]
                     if p.bench[a["bench"]].can_attack]
            pool = fresh or by_type["swap"]
            best = max(pool, key=lambda a: (
                p.bench[a["bench"]].hp + p.bench[a["bench"]].base_atk))
            return best

    # 3) 攻撃できるなら攻撃
    if "attack" in by_type:
        return by_type["attack"][0]

    # 4) 攻撃できないなら、攻撃可能なベンチと交代を試す
    if "swap" in by_type and p.battle and not p.battle.can_attack:
        fresh = [a for a in by_type["swap"] if p.bench[a["bench"]].can_attack]
        if fresh:
            return max(fresh, key=lambda a: p.bench[a["bench"]].base_atk)

    return {"type": "end_turn"}


def run_cpu_turn(g: Game, level: str = DEFAULT_CPU_LEVEL, max_steps: int = 12) -> List[str]:
    """CPU のターンを終わりまで進める。"""
    start = len(g.log)
    steps = 0
    # 人間がバトル場の繰り上げを選んでいる間は、CPUは何もせず待つ
    while (g.winner is None and not g.waiting_for_human_choice()
           and g.players[g.current].is_cpu and steps < max_steps):
        act = choose_action(g, level)
        if act["type"] == "end_turn":
            g.apply_action(act)
            break
        if not g.apply_action(act):
            g.apply_action({"type": "end_turn"})
            break
        steps += 1
    else:
        # 人間の選択待ちで抜けた場合はターンを終わらせない。
        # 選び終わったらここへ戻ってきて、CPUは続きを指す。
        if (g.winner is None and not g.waiting_for_human_choice()
                and g.players[g.current].is_cpu):
            g.apply_action({"type": "end_turn"})
    return g.log[start:]
