# -*- coding: utf-8 -*-
"""
ゲーム進行エンジン。

UI には一切依存しない。ターミナルからでも Web からでも同じ API で動かせる。

  game = Game()
  game.start()
  for a in game.legal_actions(): ...
  game.apply_action({"type": "attack"})
  game.view(0)   # プレイヤー0 から見た盤面（相手の手札は隠される）
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .cards import (BALANCE, Card, build_item_deck, build_monster_deck)

B = BALANCE
AV = B["ability_values"]
DEMON = B["demon_lord"]

# ゲームオプション。新しいゲームを始めるときに指定する。
#   monster_abilities … J/Q/K/A の特殊能力を使うか。オフだとルールがぐっと単純になる
#   demon_lord        … ♠A の魔王を使うか（技オフのときは自動的にオフ扱い）
DEFAULT_OPTIONS = {
    "monster_abilities": True,
    "demon_lord": True,
}

OPTION_LABELS = {
    "monster_abilities": "モンスターの技",
    "demon_lord": "魔王（♠A）",
}


# ==========================================================================
# 場に出ているモンスター1体分の状態
# ==========================================================================
@dataclass
class Monster:
    card: Card
    uid: int
    hp: int
    hp_max: int
    base_atk: int
    base_def: int
    attacks_used: int = 0
    fatigue: int = 0          # >0 の間は攻撃できない（ターン開始時に1減る）
    poison: int = 0           # 毎ターン受ける継続ダメージ
    curse: int = 0            # 魔剣などの自傷ダメージ
    atk_bonus: int = 0
    def_bonus: int = 0
    fragile_atk: int = 0      # 伝説の剣：1回攻撃すると失われる分
    equipment: List[str] = field(default_factory=list)
    revived: bool = False     # 不死鳥を使ったか
    is_demon: bool = False
    demon_turns: int = 0
    ability_enabled: bool = True   # 「技なし」オプション時は False

    @property
    def ability_id(self) -> Optional[str]:
        if not self.ability_enabled:
            return None
        return self.card.ability.id if self.card.ability else None

    @property
    def can_attack(self) -> bool:
        return self.fatigue <= 0

    def to_dict(self) -> dict:
        d = self.card.to_dict()
        if not self.ability_enabled:
            d.pop("ability", None)
        d.update({
            "uid": self.uid,
            "hp": self.hp,
            "hp_max": self.hp_max,
            "atk_now": self.base_atk + self.atk_bonus,
            "def_now": self.base_def + self.def_bonus,
            "attacks_used": self.attacks_used,
            "attacks_left": max(0, B["attacks_before_retire"] - self.attacks_used),
            "fatigue": self.fatigue,
            "poison": self.poison,
            "curse": self.curse,
            "equipment": list(self.equipment),
            "is_demon": self.is_demon,
            "demon_turns": self.demon_turns,
            "revived": self.revived,
        })
        if self.is_demon:
            d["name"] = "魔王"
            d["mark"] = "👹"
        return d


# ==========================================================================
# プレイヤー1人分の状態
# ==========================================================================
@dataclass
class Player:
    idx: int
    name: str
    is_cpu: bool
    trainer_hp: int
    trainer_hp_max: int
    deck: List[Card] = field(default_factory=list)
    discard: List[Card] = field(default_factory=list)
    battle: Optional[Monster] = None
    bench: List[Optional[Monster]] = field(default_factory=list)
    hand: List[Card] = field(default_factory=list)
    item_used: bool = False
    swaps_left: int = 0
    attacked: bool = False

    def field_monsters(self) -> List[Monster]:
        out = []
        if self.battle:
            out.append(self.battle)
        out.extend([m for m in self.bench if m])
        return out

    def has_bench_ability(self, ability_id: str) -> bool:
        return any(m and m.ability_id == ability_id for m in self.bench)


# ==========================================================================
# ゲーム本体
# ==========================================================================
class Game:
    MAX_TURNS = 200

    def __init__(self, seed: Optional[int] = None,
                 names=("あなた", "CPU"), cpu=(False, True),
                 options: Optional[dict] = None):
        self.options = dict(DEFAULT_OPTIONS)
        if options:
            # 知らないキーは無視する（古い設定が残っていても壊れないように）
            for k in DEFAULT_OPTIONS:
                if k in options:
                    self.options[k] = bool(options[k])
        # 技オフなら魔王も出ない（魔王は ♠A の技なので）
        if not self.options["monster_abilities"]:
            self.options["demon_lord"] = False
        self.rng = random.Random(seed)
        self.uid_seq = 0
        self.turn = 0
        self.current = 0
        self.winner: Optional[int] = None
        self.finish_reason = ""
        self.log: List[str] = []
        self.players = [
            Player(idx=i, name=names[i], is_cpu=cpu[i],
                   trainer_hp=B["trainer_hp"], trainer_hp_max=B["trainer_hp"],
                   bench=[None] * B["bench_size"])
            for i in range(2)
        ]
        self.item_deck: List[Card] = []
        self.item_discard: List[Card] = []

    # ---------------------------------------------------------------- setup
    def start(self):
        for p in self.players:
            p.deck = build_monster_deck()
            self.rng.shuffle(p.deck)
        self.item_deck = build_item_deck()
        self.rng.shuffle(self.item_deck)

        for p in self.players:
            for _ in range(B["initial_hand_size"]):
                self._draw_item(p, silent=True)
            self._refill_field(p, silent=True)

        self.turn = 1
        self.current = 0
        self._say("=== ゲーム開始！先攻は {} ===".format(self.players[0].name))
        self._begin_turn()

    def _next_uid(self) -> int:
        self.uid_seq += 1
        return self.uid_seq

    def _say(self, msg: str):
        self.log.append(msg)

    # ------------------------------------------------------------ 山札操作
    def _draw_monster(self, p: Player) -> Optional[Card]:
        if not p.deck:
            monsters = [c for c in p.discard if c.kind == "monster"]
            if not monsters:
                return None
            p.discard = [c for c in p.discard if c.kind != "monster"]
            p.deck = monsters
            self.rng.shuffle(p.deck)
            self._say("♻️ {} の捨て札をシャッフルして山札を再構築".format(p.name))
        return p.deck.pop() if p.deck else None

    def _draw_item(self, p: Player, silent: bool = False) -> Optional[Card]:
        if len(p.hand) >= B["hand_size_max"]:
            return None
        if not self.item_deck:
            if not self.item_discard:
                return None
            self.item_deck = self.item_discard
            self.item_discard = []
            self.rng.shuffle(self.item_deck)
            if not silent:
                self._say("♻️ アイテムの捨て札をシャッフルして山札を再構築")
        if not self.item_deck:
            return None
        c = self.item_deck.pop()
        p.hand.append(c)
        return c

    def _spawn(self, p: Player, card: Card) -> Monster:
        m = Monster(card=card, uid=self._next_uid(),
                    hp=B["monster_hp"], hp_max=B["monster_hp"],
                    base_atk=card.atk, base_def=card.dfn,
                    ability_enabled=self.options["monster_abilities"])
        return m

    # --------------------------------------------------------------- 場補充
    def _refill_field(self, p: Player, silent: bool = False):
        """バトル場・ベンチの空きを埋める。バトル場はベンチからの繰り上げを優先。"""
        if p.battle is None:
            candidates = [(i, m) for i, m in enumerate(p.bench) if m]
            if candidates:
                # ベンチで一番元気なものを繰り上げる
                i, m = max(candidates, key=lambda t: (t[1].hp, t[1].base_atk))
                p.bench[i] = None
                p.battle = m
                if not silent:
                    self._say("🔀 {}：ベンチの {} がバトル場へ".format(p.name, self._nm(m)))
            else:
                card = self._draw_monster(p)
                if card:
                    p.battle = self._spawn(p, card)
                    if not silent:
                        self._say("🆕 {}：バトル場に {} が登場".format(p.name, self._nm(p.battle)))
                    self._on_enter(p, p.battle, silent)

        for i in range(len(p.bench)):
            if p.bench[i] is None:
                card = self._draw_monster(p)
                if not card:
                    break
                p.bench[i] = self._spawn(p, card)
                if not silent:
                    self._say("🆕 {}：ベンチに {} が登場".format(p.name, self._nm(p.bench[i])))
                self._on_enter(p, p.bench[i], silent)

    def _nm(self, m: Monster) -> str:
        return "魔王" if m.is_demon else "{} {}".format(m.card.label, m.card.name)

    # ----------------------------------------------------------- 登場時効果
    def _on_enter(self, p: Player, m: Monster, silent: bool = False):
        aid = m.ability_id
        if aid == "S_A_demon" and not self.options["demon_lord"]:
            return  # 魔王なしオプション。♠A はただのカードとして場に残る
        if aid == "S_A_demon":
            m.is_demon = True
            m.hp = m.hp_max = DEMON["hp"]
            m.base_atk = DEMON["atk"]
            m.base_def = DEMON["def"]
            m.demon_turns = DEMON["turns"]
            self._say("👹 {} が魔王を降臨させた！（{}ターンで消滅）".format(p.name, DEMON["turns"]))
        elif aid == "H_K_holy":
            v = AV["H_K_trainer_heal"]
            p.trainer_hp = min(p.trainer_hp_max, p.trainer_hp + v)
            self._say("✨ 聖王の加護：{} のトレーナーHPが{}回復".format(p.name, v))
        elif aid == "C_Q_scheme":
            for _ in range(AV["C_Q_draw"]):
                self._draw_item(p, silent=True)
            self._say("📜 策謀のクイーン：{} がアイテムを{}枚引いた".format(p.name, AV["C_Q_draw"]))
        elif aid == "C_A_sage":
            n = 0
            while len(p.hand) < B["hand_size_max"]:
                if self._draw_item(p, silent=True) is None:
                    break
                n += 1
            self._say("🔮 賢者：{} がアイテムを{}枚補充".format(p.name, n))

    # ============================================================ ターン進行
    def _begin_turn(self):
        p = self.players[self.current]
        o = self.players[1 - self.current]
        p.item_used = False
        p.swaps_left = 1
        p.attacked = False
        self._say("──── ターン{}：{} ────".format(self.turn, p.name))

        # 疲労回復
        for m in p.field_monsters():
            if m.fatigue > 0:
                m.fatigue -= 1

        # 毒・呪いの継続ダメージ
        for m in list(p.field_monsters()):
            tick = m.poison + m.curse
            if tick > 0:
                self._damage_monster(p, m, tick, source="継続ダメージ", by_opponent=False)

        # ターン開始時の技
        for m in p.field_monsters():
            if m.ability_id == "H_J_regen":
                v = AV["H_J_regen"]
                for t in p.field_monsters():
                    t.hp = min(t.hp_max, t.hp + v)
                self._say("💚 ヒーリングナイト：{} の場のモンスターが{}回復".format(p.name, v))
                break

        # 魔王のカウントダウン
        for m in list(p.field_monsters()):
            if m.is_demon and m.demon_turns > 0:
                m.demon_turns -= 1
                if m.demon_turns <= 0:
                    self._say("👹 {} の魔王が消滅した".format(p.name))
                    self._remove(p, m, to_discard=True)

        if self.winner is None:
            self._refill_field(p)
            self._draw_item(p)
        self._check_end()

    def end_turn(self):
        if self.winner is not None:
            return
        self.turn += 1
        self.current = 1 - self.current
        if self.turn > self.MAX_TURNS:
            self._finish_by_hp("ターン上限")
            return
        self._begin_turn()

    # ============================================================== 行動候補
    def legal_actions(self, idx: Optional[int] = None) -> List[dict]:
        if self.winner is not None:
            return []
        idx = self.current if idx is None else idx
        if idx != self.current:
            return []
        p = self.players[idx]
        o = self.players[1 - idx]
        acts: List[dict] = []

        # 攻撃
        if p.battle and not p.attacked and p.battle.can_attack:
            if not (p.battle.is_demon and o.battle and o.battle.is_demon):
                target = "相手トレーナー（直接攻撃）" if o.battle is None else self._nm(o.battle)
                acts.append({"type": "attack", "label": "⚔️ 攻撃 → {}".format(target)})

        # 交代
        if p.swaps_left > 0:
            for i, m in enumerate(p.bench):
                if m:
                    acts.append({"type": "swap", "bench": i,
                                 "label": "🔄 交代 → {}".format(self._nm(m))})

        # アイテム
        if not p.item_used:
            for i, c in enumerate(p.hand):
                if self._item_usable(p, o, c):
                    acts.append({"type": "item", "hand": i,
                                 "label": "🎒 {}".format(c.effect.text)})

        acts.append({"type": "end_turn", "label": "⏭️ ターン終了"})
        return acts

    def _item_usable(self, p: Player, o: Player, c: Card) -> bool:
        t = c.effect.type
        if t in ("heal", "full_heal", "weapon", "armor", "weapon_cursed",
                 "weapon_fragile", "cure_fatigue", "sacrifice"):
            if p.battle is None:
                return False
            if t == "cure_fatigue":
                return p.battle.fatigue > 0
            if t in ("heal", "full_heal"):
                return p.battle.hp < p.battle.hp_max
            return True
        if t in ("burn", "poison", "stun", "forbidden"):
            return o.battle is not None
        if t == "trainer_heal":
            return p.trainer_hp < p.trainer_hp_max
        if t == "free_swap":
            return any(m for m in p.bench)
        if t == "deploy":
            return any(m is None for m in p.bench)
        if t == "draw_items":
            return len(p.hand) < B["hand_size_max"]
        if t == "revive":
            return any(x.kind == "monster" for x in p.discard) and any(m is None for m in p.bench)
        return True

    # ============================================================== 行動実行
    def apply_action(self, action: dict) -> bool:
        if self.winner is not None:
            return False
        p = self.players[self.current]
        o = self.players[1 - self.current]
        t = action.get("type")

        if t == "attack":
            if not (p.battle and not p.attacked and p.battle.can_attack):
                return False
            if p.battle.is_demon and o.battle and o.battle.is_demon:
                return False
            self._do_attack(p, o)
        elif t == "swap":
            i = action.get("bench", -1)
            if p.swaps_left <= 0 or not (0 <= i < len(p.bench)) or p.bench[i] is None:
                return False
            p.swaps_left -= 1
            p.battle, p.bench[i] = p.bench[i], p.battle
            self._say("🔄 {}：{} と交代".format(p.name, self._nm(p.battle)))
        elif t == "item":
            i = action.get("hand", -1)
            if p.item_used or not (0 <= i < len(p.hand)):
                return False
            c = p.hand[i]
            if not self._item_usable(p, o, c):
                return False
            p.hand.pop(i)
            self.item_discard.append(c)
            p.item_used = True
            self._use_item(p, o, c)
        elif t == "end_turn":
            self.end_turn()
            return True
        else:
            return False

        self._check_end()
        return True

    # ================================================================== 戦闘
    def _effective_atk(self, p: Player, m: Monster) -> int:
        v = m.base_atk + m.atk_bonus
        if p.has_bench_ability("C_K_command"):
            v += AV["C_K_command"]
        return v

    def _effective_def(self, p: Player, m: Monster) -> int:
        v = m.base_def + m.def_bonus
        if p.has_bench_ability("H_Q_guard"):
            v += AV["H_Q_guard"]
        return v

    def _do_attack(self, p: Player, o: Player):
        a = p.battle
        p.attacked = True
        atk = self._effective_atk(p, a)
        aid = a.ability_id

        # 直接攻撃（相手の場が空）
        if o.battle is None:
            if aid == "S_J_reckless":
                atk += AV["S_J_reckless_bonus"]
            o.trainer_hp -= atk
            self._say("💥 {} の {} が直接攻撃！{} のトレーナーに{}ダメージ".format(
                p.name, self._nm(a), o.name, atk))
        else:
            d = o.battle
            dfn = self._effective_def(o, d)
            if aid == "D_Q_pierce":
                dfn = int(dfn * AV["D_Q_pierce_rate"])
                self._say("🗡️ ピアススピア：相手の防御を{}%として計算".format(
                    int(AV["D_Q_pierce_rate"] * 100)))
            if aid == "S_J_reckless":
                atk += AV["S_J_reckless_bonus"]
            dmg = max(B["min_damage"], atk - dfn)
            self._say("⚔️ {} の {}（攻{}）→ {} の {}（防{}）に {}ダメージ".format(
                p.name, self._nm(a), atk, o.name, self._nm(d), dfn, dmg))

            # 攻撃時の追加効果
            if aid == "D_K_destroyer":
                v = AV["D_K_trainer_damage"]
                o.trainer_hp -= v
                self._say("💀 破壊王：{} のトレーナーにも{}ダメージ".format(o.name, v))
            if aid == "S_Q_poison":
                d.poison = max(d.poison, AV["S_Q_poison"])
                self._say("☠️ ポイズンクイーン：{} が毒状態に".format(self._nm(d)))
            if aid == "C_J_disturb":
                d.fatigue = max(d.fatigue, B["fatigue_turns"])
                self._say("🌀 トリックスター：{} を疲労させた".format(self._nm(d)))
            if aid == "D_J_splash":
                v = AV["D_J_splash"]
                for bm in [m for m in o.bench if m]:
                    self._damage_monster(o, bm, v, source="デュアルブレイド", by_opponent=True)
                self._say("🌪️ デュアルブレイド：相手ベンチ全体に{}ダメージ".format(v))

            self._damage_monster(o, d, dmg, source="攻撃", by_opponent=True)

        # 反動ダメージ
        if aid == "S_J_reckless":
            self._damage_monster(p, a, AV["S_J_reckless_recoil"], source="反動", by_opponent=False)
        if aid == "S_K_tyrant":
            self._damage_monster(p, a, AV["S_K_tyrant_recoil"], source="暴君の代償", by_opponent=False)

        if p.battle is not a:  # 反動で自滅した
            return

        # 伝説の剣は1回で壊れる
        if a.fragile_atk:
            a.atk_bonus -= a.fragile_atk
            a.fragile_atk = 0
            if "伝説の剣" in a.equipment:
                a.equipment.remove("伝説の剣")
            self._say("💔 伝説の剣が砕け散った")

        # 疲労と強制退場
        a.attacks_used += 1
        if aid == "D_A_onehit":
            self._say("☄️ 一撃必殺：{} は役目を終えて退場".format(self._nm(a)))
            self._remove(p, a, to_discard=True)
            return
        if aid != "S_K_tyrant":
            a.fatigue = B["fatigue_turns"]
            self._say("😴 {} は疲労した".format(self._nm(a)))
        else:
            self._say("👑 暴君は疲労しない")

        if a.attacks_used >= B["attacks_before_retire"]:
            self._say("🚪 {} は{}回攻撃したので強制退場".format(self._nm(a), a.attacks_used))
            self._remove(p, a, to_discard=True)

    # ------------------------------------------------------ ダメージ／退場
    def _damage_monster(self, owner: Player, m: Monster, dmg: int,
                        source: str = "", by_opponent: bool = True):
        if dmg <= 0 or m.hp <= 0:
            return
        m.hp -= dmg
        if source == "継続ダメージ":
            self._say("🩸 {} の {} が{}で{}ダメージ".format(owner.name, self._nm(m), source, dmg))
        if m.hp <= 0:
            self._defeat(owner, m, by_opponent)

    def _defeat(self, owner: Player, m: Monster, by_opponent: bool):
        # 不死鳥：1度だけ全快で復活
        if m.ability_id == "H_A_phoenix" and not m.revived:
            m.revived = True
            m.hp = m.hp_max
            m.poison = 0
            self._say("🔥 不死鳥が蘇った！{} はHP全快で復活".format(self._nm(m)))
            return
        self._say("☠️ {} の {} が倒れた".format(owner.name, self._nm(m)))
        self._remove(owner, m, to_discard=True)
        if by_opponent:
            v = B["kill_trainer_damage"]
            owner.trainer_hp -= v
            self._say("💢 {} のトレーナーに{}ダメージ".format(owner.name, v))

    def _remove(self, owner: Player, m: Monster, to_discard: bool = True):
        if owner.battle is m:
            owner.battle = None
        for i, b in enumerate(owner.bench):
            if b is m:
                owner.bench[i] = None
        if to_discard:
            owner.discard.append(m.card)
        self._refill_field(owner)

    # ================================================================ アイテム
    def _use_item(self, p: Player, o: Player, c: Card):
        e = c.effect
        t, v = e.type, e.value
        self._say("🎒 {} が「{}」を使用".format(p.name, c.name))

        if t == "heal":
            p.battle.hp = min(p.battle.hp_max, p.battle.hp + v)
            self._say("💚 {} のHPが{}回復（{}/{}）".format(
                self._nm(p.battle), v, p.battle.hp, p.battle.hp_max))
        elif t == "full_heal":
            p.battle.hp = p.battle.hp_max
            p.battle.poison = 0
            self._say("💚 {} のHPが全回復".format(self._nm(p.battle)))
        elif t == "trainer_heal":
            p.trainer_hp = min(p.trainer_hp_max, p.trainer_hp + v)
            self._say("✨ トレーナーHPが{}回復（{}）".format(v, p.trainer_hp))
        elif t == "weapon":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v))
        elif t == "armor":
            p.battle.def_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🛡️ {} の防御+{}".format(self._nm(p.battle), v))
        elif t == "weapon_cursed":
            p.battle.atk_bonus += v
            p.battle.curse += e.extra
            p.battle.equipment.append("魔剣(+{})".format(v))
            self._say("🗡️ {} の攻撃+{}（毎ターン{}の自傷）".format(self._nm(p.battle), v, e.extra))
        elif t == "weapon_fragile":
            p.battle.atk_bonus += v
            p.battle.fragile_atk += v
            p.battle.equipment.append("伝説の剣")
            self._say("⚔️ {} の攻撃+{}（1回攻撃で壊れる）".format(self._nm(p.battle), v))
        elif t == "burn":
            self._say("🔥 {} に{}ダメージ".format(self._nm(o.battle), v))
            self._damage_monster(o, o.battle, v, source="呪符", by_opponent=True)
            if e.extra and p.battle:
                self._say("🩸 反動で自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra))
                self._damage_monster(p, p.battle, e.extra, source="反動", by_opponent=False)
        elif t == "poison":
            o.battle.poison = max(o.battle.poison, v)
            self._say("☠️ {} が毒状態に（毎ターン{}）".format(self._nm(o.battle), v))
        elif t == "stun":
            o.battle.fatigue = max(o.battle.fatigue, B["fatigue_turns"])
            self._say("🌀 {} は次のターン攻撃できない".format(self._nm(o.battle)))
        elif t == "cure_fatigue":
            p.battle.fatigue = 0
            self._say("⚡ {} の疲労が回復".format(self._nm(p.battle)))
        elif t == "free_swap":
            p.swaps_left += 1
            self._say("🔄 交代権を1回追加")
        elif t == "deploy":
            for i, m in enumerate(p.bench):
                if m is None:
                    card = self._draw_monster(p)
                    if card:
                        p.bench[i] = self._spawn(p, card)
                        self._say("🆕 号令：ベンチに {} が登場".format(self._nm(p.bench[i])))
                        self._on_enter(p, p.bench[i])
                    break
        elif t == "draw_items":
            n = 0
            for _ in range(v):
                if self._draw_item(p) is None:
                    break
                n += 1
            self._say("📜 アイテムを{}枚引いた".format(n))
        elif t == "revive":
            monsters = [x for x in p.discard if x.kind == "monster"]
            if monsters:
                best = max(monsters, key=lambda x: x.atk + x.dfn)
                p.discard.remove(best)
                for i, m in enumerate(p.bench):
                    if m is None:
                        p.bench[i] = self._spawn(p, best)
                        self._say("🕊️ 蘇生：{} がベンチに戻った".format(self._nm(p.bench[i])))
                        self._on_enter(p, p.bench[i])
                        break
        elif t == "sacrifice":
            target = p.battle
            self._say("🩸 生贄の儀式：{} を捧げた".format(self._nm(target)))
            self._remove(p, target, to_discard=True)
            o.trainer_hp -= v
            self._say("💢 {} のトレーナーに{}ダメージ".format(o.name, v))
        elif t == "forbidden":
            p.trainer_hp -= v
            self._say("🕯️ 禁断の契約：自分のトレーナーHP-{}".format(v))
            target = o.battle
            if target:
                self._say("🌑 {} を強制退場させた".format(self._nm(target)))
                self._remove(o, target, to_discard=True)

    # ================================================================== 終了
    def _check_end(self):
        if self.winner is not None:
            return
        a, b = self.players
        if a.trainer_hp <= 0 and b.trainer_hp <= 0:
            self._finish_by_hp("相打ち")
        elif a.trainer_hp <= 0:
            self.winner = 1
            self.finish_reason = "{} のトレーナーHPが0になった".format(a.name)
            self._say("🏆 {} の勝ち！".format(b.name))
        elif b.trainer_hp <= 0:
            self.winner = 0
            self.finish_reason = "{} のトレーナーHPが0になった".format(b.name)
            self._say("🏆 {} の勝ち！".format(a.name))

    def _finish_by_hp(self, reason: str):
        a, b = self.players
        if a.trainer_hp == b.trainer_hp:
            self.winner = -1
        else:
            self.winner = 0 if a.trainer_hp > b.trainer_hp else 1
        self.finish_reason = reason
        self._say("🏁 {}：残りHPで判定".format(reason))

    # ============================================================ 盤面の公開
    def view(self, viewer: int) -> dict:
        """viewer から見た盤面。相手の手札・山札の中身は含めない。"""
        me = self.players[viewer]
        op = self.players[1 - viewer]

        def side(p: Player, hide_hand: bool) -> dict:
            return {
                "name": p.name,
                "is_cpu": p.is_cpu,
                "trainer_hp": p.trainer_hp,
                "trainer_hp_max": p.trainer_hp_max,
                "battle": p.battle.to_dict() if p.battle else None,
                "bench": [m.to_dict() if m else None for m in p.bench],
                "hand": ([] if hide_hand else [c.to_dict() for c in p.hand]),
                "hand_count": len(p.hand),
                "deck_count": len(p.deck),
                "discard_count": len(p.discard),
                "item_used": p.item_used,
                "swaps_left": p.swaps_left,
                "attacked": p.attacked,
            }

        return {
            "turn": self.turn,
            "current": self.current,
            "options": dict(self.options),
            "option_labels": dict(OPTION_LABELS),
            "is_my_turn": self.current == viewer,
            "viewer": viewer,
            "me": side(me, hide_hand=False),
            "opponent": side(op, hide_hand=True),
            "item_deck_count": len(self.item_deck),
            "actions": self.legal_actions(viewer),
            "winner": self.winner,
            "finish_reason": self.finish_reason,
            "log": self.log[-60:],
        }
