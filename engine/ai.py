# -*- coding: utf-8 -*-
"""
CPU プレイヤー。

ルールを理解しているだけの素直な思考ルーチン。
「まず有利なアイテムを使い、必要なら交代し、殴れるなら殴る」だけ。
強さの調整はここを差し替えれば済むように、Game からは独立させてある。
"""
from __future__ import annotations

import random
from typing import List, Optional

from .cards import BALANCE
from .game import Game, Player

B = BALANCE
AI = B["ai"]


def _score_item(g: Game, p: Player, o: Player, card) -> float:
    """そのアイテムを今使う価値をざっくり点数化する。"""
    e = card.effect
    t, v = e.type, e.value
    bm, om = p.battle, o.battle
    hp_rate = (bm.hp / bm.hp_max) if bm else 1.0

    if t in ("heal", "full_heal"):
        if not bm or hp_rate > AI["heal_hp_threshold"]:
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
        return 15
    if t == "draw_items":
        return 20
    if t == "revive":
        return 25
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


def choose_action(g: Game) -> dict:
    """CPU の1手を返す。"""
    p = g.players[g.current]
    o = g.players[1 - g.current]
    actions = g.legal_actions()
    if not actions:
        return {"type": "end_turn"}

    by_type = {}
    for a in actions:
        by_type.setdefault(a["type"], []).append(a)

    # 1) アイテム：一番点数の高いものが十分な価値ならそれを使う
    if "item" in by_type:
        best, best_score = None, 0.0
        for a in by_type["item"]:
            card = p.hand[a["hand"]]
            s = _score_item(g, p, o, card)
            if s > best_score:
                best, best_score = a, s
        if best and best_score >= 15:
            return best

    # 2) 交代：バトル場が瀕死 or 疲労中で、ベンチに動けるやつがいるなら替える
    if "swap" in by_type and p.battle:
        hp_rate = p.battle.hp / p.battle.hp_max
        stuck = p.battle.fatigue > 0
        weak = hp_rate <= AI["swap_hp_threshold"]
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


def run_cpu_turn(g: Game, max_steps: int = 12) -> List[str]:
    """CPU のターンを終わりまで進める。"""
    start = len(g.log)
    steps = 0
    while g.winner is None and g.players[g.current].is_cpu and steps < max_steps:
        act = choose_action(g)
        if act["type"] == "end_turn":
            g.apply_action(act)
            break
        if not g.apply_action(act):
            g.apply_action({"type": "end_turn"})
            break
        steps += 1
    else:
        if g.winner is None and g.players[g.current].is_cpu:
            g.apply_action({"type": "end_turn"})
    return g.log[start:]
