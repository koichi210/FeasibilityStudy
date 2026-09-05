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

# 場に置いておくだけで味方全体を支え続けるカード。
# 置きっぱなしで恒久的な効果になってしまうのを防ぐため、
# ベンチ滞在ターン数に上限を設ける。
#   H_Q_guard   … ベンチにいる間、バトル場の防御+
#   C_K_command … ベンチにいる間、バトル場の攻撃+
#   H_J_regen   … 毎ターン味方全体を回復（ベンチからでも効く）
BENCH_LIMITED_ABILITIES = {"H_Q_guard", "C_K_command", "H_J_regen"}

# アイテムを使ったときに光らせる色。効果の性質で3種類に分ける。
#   attack … 相手を攻める（赤）
#   heal   … 癒す（緑）
#   buff   … 強化・小細工（青）※ここに無いものは buff 扱い
ITEM_TONE = {
    "burn": "attack", "poison": "attack", "stun": "attack",
    "forbidden": "attack", "sacrifice": "attack",
    "heal": "heal", "full_heal": "heal", "trainer_heal": "heal", "revive": "heal",
}

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
# ログ1行分
# ==========================================================================
@dataclass
class LogEntry:
    """ログ1行。private_to が席番号なら、その人にしか見せない行。

    ベンチとモンスター手札の中身は相手に伏せているので、
    それらのカード名を含む行は private_to 付きで積む。
    view() が viewer ごとに絞ってから返すので、
    通信を覗かれても相手には流れない。
    """
    text: str
    private_to: Optional[int] = None

    def __str__(self) -> str:   # simulate.py の print 用
        return self.text


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
    bench_turns_left: Optional[int] = None  # 聖女クイーン・指揮官キング専用：
                                             # ベンチにいられる残りターン（None＝対象外）
    # 一度でもバトル場に出たか。出た時点で相手に見られているので、
    # そのあとベンチに下がっても伏せ札には戻さない（隠す意味がないため）。
    revealed: bool = False

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
            "bench_turns_left": self.bench_turns_left,
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
    monster_hand: List[Card] = field(default_factory=list)  # 引いたがまだ場に出していないモンスター
    item_used: bool = False
    swaps_left: int = 0
    attacked: bool = False
    # 呪縛：次の自分のターン、攻撃も交代もできない（アイテムだけ使える）。
    # モンスター個体ではなくプレイヤーに掛ける。個体に掛けると
    # ベンチと交代するだけで抜けられてしまうため。
    stunned: bool = False

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
        self.log: List[LogEntry] = []
        # 直近の「見せ場」。画面が攻撃モーションや被弾エフェクトを出すのに使う。
        # seq は再生済みかどうかの目印（同じ seq なら再生しない）。
        self.fx: Optional[dict] = None
        self.fx_seq = 0
        # バトル場が空いて「ベンチの誰を出すか」の選択待ちになっている席。
        # 相手のターン中に倒されることもあるので、手番とは独立して持つ。
        # 選び終わるまで、ほかの操作は受け付けない（両者が待つ）。
        self.pending_promote: List[int] = []
        # 「めくった中から選ぶ」待ち。蘇生・号令・賢者の杖で使う。
        # {"seat", "kind", "title", "cards", "picks", "to"} の形。
        # 選び終わるまで他の操作は止める（自分のターン中にしか起きない）。
        self.pending_choice: Optional[dict] = None
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
            self._refill_field(p, silent=True, instant=True)

        self.turn = 1
        self.current = 0
        self._say("=== ゲーム開始！先攻は {} ===".format(self.players[0].name))
        self._begin_turn()

    def _next_uid(self) -> int:
        self.uid_seq += 1
        return self.uid_seq

    def _say(self, msg: str, private_to: Optional[int] = None):
        """ログを1行足す。

        private_to に席番号を渡すと、その人の画面にだけ出る。
        ベンチ・モンスター手札の中身は相手に伏せているので、
        それらに触れる行は必ず private_to を付けること（付け忘れ＝情報漏洩）。
        """
        self.log.append(LogEntry(msg, private_to))

    def _fx(self, kind: str, attacker: Optional[Monster] = None,
            target: Optional[Monster] = None, title: str = "", cry: str = "",
            tone: str = ""):
        """画面に出す演出（攻撃モーション・被弾の爪痕）を1つ予約する。

        ルールには影響しない。画面側は seq を見て、まだ再生していないものだけを
        再生する（同じ盤面を描き直すたびに何度も揺れてしまうのを防ぐため）。
        """
        self.fx_seq += 1
        self.fx = {
            "seq": self.fx_seq,
            "kind": kind,
            "attacker": attacker.uid if attacker else None,
            "target": target.uid if target else None,
            # 画面中央に出す口上。title が名前、cry が叫び。
            # tone は光らせる色（attack=赤 / heal=緑 / buff=青）。
            "title": title,
            "cry": cry,
            "tone": tone,
        }

    def _say_hidden(self, owner: Player, mine: str, theirs: str):
        """伏せてある場所（ベンチ・モンスター手札）の出来事を、見せ方を変えて両者に伝える。

        owner には具体的なカード名入りの `mine` を、相手には
        カード名を伏せた `theirs` を出す。「何かが起きた」ことは伝わるが
        「何のカードか」は漏れない。
        """
        self._say(mine, private_to=owner.idx)
        self._say(theirs, private_to=1 - owner.idx)

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

    def _pop_item(self) -> Optional[Card]:
        """アイテム山札から1枚取り出す（手札には入れない）。めくって選ばせる用。"""
        if not self.item_deck:
            if not self.item_discard:
                return None
            self.item_deck = self.item_discard
            self.item_discard = []
            self.rng.shuffle(self.item_deck)
        return self.item_deck.pop() if self.item_deck else None

    def _spawn(self, p: Player, card: Card) -> Monster:
        m = Monster(card=card, uid=self._next_uid(),
                    hp=B["monster_hp"], hp_max=B["monster_hp"],
                    base_atk=card.atk, base_def=card.dfn,
                    ability_enabled=self.options["monster_abilities"])
        if m.ability_id in BENCH_LIMITED_ABILITIES:
            m.bench_turns_left = B["bench_ability_turns"]
        return m

    # --------------------------------------------------------------- 場補充
    def _refill_field(self, p: Player, silent: bool = False, instant: bool = False):
        """バトル場の繰り上げを行う（空きがあればベンチから自動で上がる）。

        モンスター手札への補充はここではやらない。アイテム手札と同じく
        `_draw_monster_to_hand` が自分のターン開始時に1枚だけ引く
        （`_begin_turn` 参照）。実際にバトル場・ベンチへ置くのは、
        プレイヤー（またはCPU）の「配置」操作（apply_action の type="place"）。

        instant=True は **ゲーム開始時専用**。手札を経由すると、先攻が
        「配置→攻撃」を済ませる間、後攻はまだ1度も配置できておらず
        バトル場が空のまま＝直接攻撃され放題、という不公平が起きる。
        それを避けるため、初期配置だけは両者同時に山札から直接場へ出す。
        """
        # バトル場が空いたときの繰り上げ。
        # 誰を出すかは戦況を左右するので、人間には選んでもらう（pending_promote）。
        # ゲーム開始時とCPUは、待たせても仕方がないので一番元気なものを自動で出す。
        if p.battle is None:
            candidates = [(i, m) for i, m in enumerate(p.bench) if m]
            if candidates and (instant or p.is_cpu):
                i, m = max(candidates, key=lambda t: (t[1].hp, t[1].base_atk))
                p.bench[i] = None
                self._stand_battle(p, m)
                if not silent:
                    self._say("🔀 {}：ベンチの {} がバトル場へ".format(p.name, self._nm(m)))
            elif candidates and self.winner is None:
                if p.idx not in self.pending_promote:
                    self.pending_promote.append(p.idx)
                    # 進行が止まる理由が分からないと不安なので、両者に知らせる。
                    # 何を選んでいるかは伏せたまま「選択中」だけを伝える。
                    if not silent:
                        self._say("🤔 {}：バトル場へ出すカードを選んでいます…".format(p.name))
            elif instant:
                card = self._draw_monster(p)
                if card:
                    self._stand_battle(p, self._spawn(p, card))
                    if not silent:
                        self._say("🆕 {}：バトル場に {} が登場".format(p.name, self._nm(p.battle)))
                    self._on_enter(p, p.battle, silent)

        if instant:
            for i in range(len(p.bench)):
                if p.bench[i] is None:
                    card = self._draw_monster(p)
                    if not card:
                        break
                    p.bench[i] = self._spawn(p, card)
                    if not silent:
                        # ベンチの中身は相手に伏せる
                        self._say_hidden(
                            p,
                            "🆕 {}：ベンチに {} が登場".format(p.name, self._nm(p.bench[i])),
                            "🆕 {}：ベンチにモンスターが1体登場".format(p.name))
                    self._on_enter(p, p.bench[i], silent)
            return

        # 選ぶ余地が無くなったら待ちを解除する
        # （誰かが出て埋まった／ベンチも全滅して選べるものが無い）
        if p.idx in self.pending_promote and (p.battle is not None or not any(p.bench)):
            self.pending_promote.remove(p.idx)

    def _stand_battle(self, p: Player, m: Optional[Monster]):
        """バトル場に立たせる。立った時点で相手に見られたことにする。"""
        p.battle = m
        if m:
            m.revealed = True

    def pending_seat(self) -> Optional[int]:
        """いま「ベンチの誰を出すか」を選ぶ番の席。誰も待っていなければ None。"""
        return self.pending_promote[0] if self.pending_promote else None

    def waiting_for_human_choice(self) -> bool:
        """人間の選択待ちで進行を止めるべきか（CPUを走らせる側が見る）。

        繰り上げ（pending_promote）と、めくったカードの選択（pending_choice）の
        どちらも対象。どちらか一方でも待っている間は、CPUを進めてはいけない。
        """
        for seat in (self.pending_seat(),
                     self.pending_choice["seat"] if self.pending_choice else None):
            if seat is not None and not self.players[seat].is_cpu:
                return True
        return False

    def _draw_monster_to_hand(self, p: Player, silent: bool = False) -> Optional[Card]:
        """モンスター手札にターン開始時1枚だけ引く（アイテム手札と同じ方式）。

        上限はアイテム手札とは別枠（monster_hand_size_max）。
        場は4枠しかないので、配置しきれない分を抱えられるよう多めにしてある。
        """
        if len(p.monster_hand) >= B["monster_hand_size_max"]:
            return None
        card = self._draw_monster(p)
        if not card:
            return None
        p.monster_hand.append(card)
        if not silent:
            # 手札の中身は相手に伏せる（引いた事実だけ伝える）
            self._say_hidden(
                p,
                "🃏 {} が {} をモンスター手札に加えた".format(
                    p.name, "{}{}".format(card.label, card.name)),
                "🃏 {} がモンスターを1枚引いた".format(p.name))
        return card

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
        # 毒＝相手が仕掛けてきたもの→倒れたら相手のせい（トレーナーダメージあり）
        # 呪い＝自分の魔剣の自傷→倒れたら自分のせい（トレーナーダメージなし）
        for m in list(p.field_monsters()):
            if m.poison > 0:
                self._damage_monster(p, m, m.poison, source="毒", by_opponent=True)
            if m.hp > 0 and m.curse > 0:
                self._damage_monster(p, m, m.curse, source="呪い", by_opponent=False)

        # ターン開始時の技
        for m in p.field_monsters():
            if m.ability_id == "H_J_regen":
                v = AV["H_J_regen"]
                for t in p.field_monsters():
                    t.hp = min(t.hp_max, t.hp + v)
                self._say("💚 ヒーリングナイト：{} の場のモンスターが{}回復".format(p.name, v))
                break

        # 魔王のカウントダウン：バトル場にいる間だけ減る。ベンチにいる間は消滅しない
        if p.battle and p.battle.is_demon and p.battle.demon_turns > 0:
            p.battle.demon_turns -= 1
            if p.battle.demon_turns <= 0:
                self._say("👹 {} の魔王が消滅した".format(p.name))
                self._remove(p, p.battle, to_discard=True)

        # 聖女クイーン・指揮官キングのベンチ滞在カウントダウン：
        # ベンチに置いておくだけの恒久バフにならないよう、上限ターンで強制退場させる。
        # バトル場にいる間はカウントしない（魔王とは逆の向き）。
        for m in list(p.bench):
            if m and m.bench_turns_left is not None:
                m.bench_turns_left -= 1
                if m.bench_turns_left <= 0:
                    self._say_hidden(
                        p,
                        "⌛ {} はベンチにいられる期限が切れて退場".format(self._nm(m)),
                        "⌛ {} のベンチのモンスターが1体、期限切れで退場".format(p.name))
                    self._remove(p, m, to_discard=True)

        if self.winner is None:
            self._refill_field(p)
            self._draw_monster_to_hand(p)
            self._draw_item(p)
        self._check_end()

    def end_turn(self):
        if self.winner is not None:
            return
        # 呪縛は「次の1ターン」だけ。縛られた本人のターンが終わったら解ける。
        self.players[self.current].stunned = False
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

        # めくったカードの選択待ち。自分のターン中にしか起きない。
        ch = self.pending_choice
        if ch:
            if idx != ch["seat"]:
                return []
            return [{"type": "pick", "index": i,
                     "label": "🎴 {}{} を選ぶ".format(c.label, c.name)}
                    for i, c in enumerate(ch["cards"])]

        # バトル場の繰り上げ待ちが最優先。選び終わるまで他の操作はできない。
        # 相手のターン中に倒された場合もここに入るので、手番は見ない。
        pend = self.pending_seat()
        if pend is not None:
            if idx != pend:
                return []
            p = self.players[idx]
            return [{"type": "promote", "bench": i,
                     "label": "🔀 {} をバトル場へ".format(self._nm(m))}
                    for i, m in enumerate(p.bench) if m]

        if idx != self.current:
            return []
        p = self.players[idx]
        o = self.players[1 - idx]
        acts: List[dict] = []

        # 攻撃（呪縛されていると出せない）
        if p.battle and not p.attacked and p.battle.can_attack and not p.stunned:
            if not (p.battle.is_demon and o.battle and o.battle.is_demon):
                target = "相手トレーナー（直接攻撃）" if o.battle is None else self._nm(o.battle)
                acts.append({"type": "attack", "label": "⚔️ 攻撃 → {}".format(target)})

        # モンスター配置（手札にいるモンスターを、空いている場に出す）
        for i, c in enumerate(p.monster_hand):
            if p.battle is None:
                acts.append({"type": "place", "hand": i, "slot": "battle",
                             "label": "🃏 {}{} をバトル場に配置".format(c.label, c.name)})
            for j, b in enumerate(p.bench):
                if b is None:
                    acts.append({"type": "place", "hand": i, "slot": j,
                                 "label": "🃏 {}{} をベンチに配置".format(c.label, c.name)})

        # 交代（呪縛されていると動けない）
        if p.swaps_left > 0 and not p.stunned:
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

    def _can_attack_with(self, m: Optional[Monster], o: Player) -> bool:
        """そのモンスターがバトル場にいたとして、いま攻撃できるか。"""
        if m is None or not m.can_attack:      # 疲労中は撃てない
            return False
        if m.is_demon and o.battle and o.battle.is_demon:   # 魔王同士は不可
            return False
        return True

    def attack_chance(self, idx: int) -> Optional[str]:
        """このターン、まだ攻撃を出せる余地があるかを返す。

        ターン終了の押し忘れ警告に使う。1ターンに1回しかない攻撃を
        使わずに終わるのはもったいないので、画面側が引き止められるようにする。

          "now"        … いますぐ攻撃できる
          "after_swap" … バトル場は疲労中などで撃てないが、
                         ベンチと交代すれば撃てる（交代しても攻撃権は残る）
          None         … どう頑張ってもこのターンは攻撃できない

        ※ 気付け薬で疲労を治す道もあるが、そこまで数えると
          「アイテムを持っているだけで毎回警告が出る」ので含めない。
        """
        if idx != self.current:
            return None
        p, o = self.players[idx], self.players[1 - idx]
        if p.attacked or p.stunned:
            return None
        if p.battle and self._can_attack_with(p.battle, o):
            return "now"
        if p.swaps_left > 0:
            for m in p.bench:
                if self._can_attack_with(m, o):
                    return "after_swap"
        return None

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
        if t == "stun":
            return not o.stunned          # 二重掛けは無意味
        if t in ("burn", "poison", "forbidden"):
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
            # 戻す先はモンスター手札なので、ベンチの空きではなく手札の空きを見る
            return (any(x.kind == "monster" for x in p.discard)
                    and len(p.monster_hand) < B["monster_hand_size_max"])
        return True

    # -------------------------------------------------- めくって選ぶ（アイテム）
    def _begin_choice(self, p: Player, kind: str, title: str,
                      cards: List[Card], picks: int, to: str):
        """候補カードを見せて、その中から選んでもらう状態に入る。

        cards はすでに山札／捨て札から取り出してある前提。
        選ばれなかったぶんは `_finish_choice` が元へ戻す。
        CPU は待たせても仕方がないので、その場で自動的に選ぶ。
        """
        if not cards:
            return
        picks = min(picks, len(cards))
        self.pending_choice = {"seat": p.idx, "kind": kind, "title": title,
                               "cards": list(cards), "picks": picks, "to": to}
        if p.is_cpu:
            while self.pending_choice:
                self._do_pick({"index": self._cpu_best_pick()})
            return
        self._say("🤔 {}：{}".format(p.name, title))

    def _cpu_best_pick(self) -> int:
        """CPU の選び方。モンスターは強いもの、アイテムは適当に先頭。"""
        cards = self.pending_choice["cards"]
        best, bi = None, 0
        for i, c in enumerate(cards):
            score = c.atk + c.dfn if c.kind == "monster" else 0
            if best is None or score > best:
                best, bi = score, i
        return bi

    def _do_pick(self, action: dict) -> bool:
        """めくった候補から1枚選ぶ。"""
        ch = self.pending_choice
        if not ch:
            return False
        i = action.get("index", -1)
        if not (0 <= i < len(ch["cards"])):
            return False
        p = self.players[ch["seat"]]
        card = ch["cards"].pop(i)

        if ch["to"] == "monster_hand":
            p.monster_hand.append(card)
            self._say_hidden(
                p,
                "🃏 {} が {}{} を選んだ".format(p.name, card.label, card.name),
                "🃏 {} がモンスターを1枚選んだ".format(p.name))
        else:                                   # アイテム手札
            p.hand.append(card)
            self._say_hidden(
                p,
                "🎒 {} が {}{} を選んだ".format(p.name, card.label, card.name),
                "🎒 {} がアイテムを1枚選んだ".format(p.name))

        ch["picks"] -= 1
        if ch["picks"] <= 0 or not ch["cards"]:
            self._finish_choice()
        return True

    def _finish_choice(self):
        """選ばれなかったカードを元へ戻して、選択待ちを終える。"""
        ch = self.pending_choice
        self.pending_choice = None
        if not ch:
            return
        rest = ch["cards"]
        if not rest:
            return
        p = self.players[ch["seat"]]
        if ch["kind"] == "revive":
            p.discard.extend(rest)              # 捨て札はそのまま戻す
        elif ch["to"] == "monster_hand":
            p.deck.extend(rest)                 # 山札へ戻して混ぜる
            self.rng.shuffle(p.deck)
        else:
            self.item_deck.extend(rest)
            self.rng.shuffle(self.item_deck)

    def _do_promote(self, action: dict) -> bool:
        """空いたバトル場に、選ばれたベンチのモンスターを繰り上げる。"""
        seat = self.pending_seat()
        if seat is None:
            return False
        p = self.players[seat]
        i = action.get("bench", -1)
        if p.battle is not None or not (0 <= i < len(p.bench)) or p.bench[i] is None:
            return False
        m = p.bench[i]
        p.bench[i] = None
        self._stand_battle(p, m)
        self.pending_promote.remove(seat)
        # バトル場は公開領域なので、カード名を出してよい
        self._say("🔀 {}：ベンチの {} をバトル場へ出した".format(p.name, self._nm(m)))
        self._check_end()
        return True

    # ============================================================== 行動実行
    def apply_action(self, action: dict) -> bool:
        if self.winner is not None:
            return False

        # めくったカードの選択が最優先
        if action.get("type") == "pick":
            return self._do_pick(action)
        if self.pending_choice:
            return False      # 選び終わるまで他の操作は止める

        # バトル場の繰り上げ選択。相手のターン中にも起こるので、
        # 手番を見ずに、選ぶ権利のある人の操作として先に処理する。
        if action.get("type") == "promote":
            return self._do_promote(action)
        if self.pending_promote:
            return False      # 誰かが選び終わるまで、他の操作は止める

        p = self.players[self.current]
        o = self.players[1 - self.current]
        t = action.get("type")

        if t == "attack":
            if p.stunned:
                return False
            if not (p.battle and not p.attacked and p.battle.can_attack):
                return False
            if p.battle.is_demon and o.battle and o.battle.is_demon:
                return False
            self._do_attack(p, o)
        elif t == "swap":
            i = action.get("bench", -1)
            if p.stunned:
                return False
            if p.swaps_left <= 0 or not (0 <= i < len(p.bench)) or p.bench[i] is None:
                return False
            p.swaps_left -= 1
            coming = p.bench[i]
            p.bench[i] = p.battle
            self._stand_battle(p, coming)
            self._say("🔄 {}：{} と交代".format(p.name, self._nm(p.battle)))
        elif t == "place":
            i = action.get("hand", -1)
            slot = action.get("slot")
            if not (0 <= i < len(p.monster_hand)):
                return False
            if slot == "battle":
                if p.battle is not None:
                    return False
                card = p.monster_hand.pop(i)
                self._stand_battle(p, self._spawn(p, card))
                self._say("🆕 {}：バトル場に {} が登場".format(p.name, self._nm(p.battle)))
                self._on_enter(p, p.battle)
            elif isinstance(slot, int) and 0 <= slot < len(p.bench) and p.bench[slot] is None:
                card = p.monster_hand.pop(i)
                p.bench[slot] = self._spawn(p, card)
                # ベンチは伏せ札なので、相手にはカード名を出さない
                self._say_hidden(
                    p,
                    "🆕 {}：ベンチに {} が登場".format(p.name, self._nm(p.bench[slot])),
                    "🆕 {}：ベンチにモンスターを1体配置".format(p.name))
                self._on_enter(p, p.bench[slot])
            else:
                return False
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
        # 攻撃した側は身構えて揺れ、殴られた側には爪痕が走る
        cry = "いけっ、{}！".format(a.card.name if not a.is_demon else "魔王")
        self._fx("attack", attacker=a, target=o.battle,
                 title="⚔️ {} の こうげき".format(self._nm(a)), cry=cry, tone="attack")
        # 誰が仕掛けたのかが一目で分かるよう、名乗りを上げてから斬りかかる
        self._say("🗣️ {}「{}」".format(p.name, cry))

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

        # 魔王は攻撃してもカウントが進む。
        # 「攻撃 → ベンチへ退避」を繰り返すとターン開始時のカウントを踏まず、
        # 実質いつまでも居座れてしまう抜け穴があったため。
        if a.is_demon and a.demon_turns > 0:
            a.demon_turns -= 1
            if a.demon_turns <= 0:
                self._say("👹 {} の魔王が力を使い果たして消滅した".format(p.name))
                self._remove(p, a, to_discard=True)
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
        if source in ("毒", "呪い"):
            self._say_visible(
                owner, m,
                "🩸 {} の {} が{}の継続ダメージで{}ダメージ".format(
                    owner.name, self._nm(m), source, dmg),
                "🩸 {} のベンチのモンスターが{}の継続ダメージで{}ダメージ".format(
                    owner.name, source, dmg))
        if m.hp <= 0:
            self._defeat(owner, m, by_opponent)

    def _say_visible(self, owner: Player, m: Monster, mine: str, theirs: str):
        """モンスターの居場所に応じてログの見せ方を切り替える。

        バトル場は公開情報なのでそのまま全員に出す。
        ベンチは伏せ札なので、相手にはカード名を伏せた `theirs` を出す。
        """
        if owner.battle is m:
            self._say(mine)
        else:
            self._say_hidden(owner, mine, theirs)

    def _defeat(self, owner: Player, m: Monster, by_opponent: bool):
        # 不死鳥：1度だけ全快で復活
        if m.ability_id == "H_A_phoenix" and not m.revived:
            m.revived = True
            m.hp = m.hp_max
            m.poison = 0
            self._say_visible(
                owner, m,
                "🔥 不死鳥が蘇った！{} はHP全快で復活".format(self._nm(m)),
                "🔥 {} のベンチで不死鳥が蘇った".format(owner.name))
            return
        self._say_visible(
            owner, m,
            "☠️ {} の {} が倒れた".format(owner.name, self._nm(m)),
            "☠️ {} のベンチのモンスターが1体倒れた".format(owner.name))
        # 撃破ダメージは「倒れた」の直後に出す。
        # 先に _remove すると、そこから出る繰り上げの案内が間に割り込んでしまう。
        if by_opponent:
            v = B["kill_trainer_damage"]
            owner.trainer_hp -= v
            self._say("💢 {} のトレーナーに{}ダメージ".format(owner.name, v))
        self._remove(owner, m, to_discard=True)

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
        if e.cry:
            self._say("🗣️ {}「{}」".format(p.name, e.cry))
        # 画面中央に大きく出す。色は効果の性質で分ける（赤=攻め / 緑=癒し / 青=強化）
        self._fx("item", title="🎒 {}".format(c.name), cry=e.cry,
                 tone=ITEM_TONE.get(t, "buff"))

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
            # 直前のアイテム演出に、被弾の相手を書き足す（別の演出にはしない）
            if self.fx:
                self.fx["target"] = o.battle.uid
            self._damage_monster(o, o.battle, v, source="呪符", by_opponent=True)
            if e.extra and p.battle:
                self._say("🩸 反動で自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra))
                self._damage_monster(p, p.battle, e.extra, source="反動", by_opponent=False)
        elif t == "poison":
            o.battle.poison = max(o.battle.poison, v)
            self._say("☠️ {} が毒状態に（毎ターン{}）".format(self._nm(o.battle), v))
        elif t == "stun":
            # モンスターではなくプレイヤーを縛る。交代で逃げられないように。
            o.stunned = True
            self._say("🌀 {} は次のターン、攻撃も交代もできない".format(o.name))
        elif t == "cure_fatigue":
            p.battle.fatigue = 0
            self._say("⚡ {} の疲労が回復".format(self._nm(p.battle)))
        elif t == "free_swap":
            p.swaps_left += 1
            self._say("🔄 交代権を1回追加")
        elif t == "deploy":
            # 山札の上から数枚めくって、その中から選ぶ。
            # 山札全部から選べると欲しいカードが必ず来てしまうので、候補を絞る。
            if len(p.monster_hand) >= B["monster_hand_size_max"]:
                self._say("🚫 号令：モンスター手札が上限で追加できなかった")
            else:
                look = [c for c in (self._draw_monster(p)
                                    for _ in range(B["look_at_cards"])) if c]
                self._begin_choice(p, "deploy",
                                   "号令：めくった{}枚から1枚選ぶ".format(len(look)),
                                   look, 1, "monster_hand")
        elif t == "draw_items":
            look = []
            for _ in range(B["look_at_cards"] + v):
                c2 = self._pop_item()
                if c2 is None:
                    break
                look.append(c2)
            self._begin_choice(p, "draw_items",
                               "賢者の杖：めくった{}枚から{}枚選ぶ".format(len(look), v),
                               look, v, "hand")
        elif t == "revive":
            # 捨て札は中身が分かっているので、こちらは全部から自由に選べる
            if len(p.monster_hand) >= B["monster_hand_size_max"]:
                self._say("🚫 蘇生：モンスター手札が上限で戻せなかった")
            else:
                monsters = [x for x in p.discard if x.kind == "monster"]
                for x in monsters:
                    p.discard.remove(x)
                self._begin_choice(p, "revive", "蘇生：捨て札から1枚選ぶ",
                                   monsters, 1, "monster_hand")
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
                # 相手のモンスターを葬った扱い。倒したのはこちらなので
                # 相手トレーナーにも撃破ダメージが入る（_remove では入らない）
                self._say("🌑 {} を葬り去った".format(self._nm(target)))
                self._defeat(o, target, by_opponent=True)

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
        """viewer から見た盤面。相手の手札・山札の中身・ベンチの中身は含めない。

        バトル場は攻撃対象になるので常に公開。ベンチは伏せ札扱いで、
        相手には「何体いるか」だけが伝わり、中身（名前・技・HPなど）は隠す。
        """
        me = self.players[viewer]
        op = self.players[1 - viewer]

        def side(p: Player, hide_hand: bool) -> dict:
            # ベンチは伏せ札。ただし一度バトル場に出たカードは既に見られているので、
            # ベンチへ下がってもそのまま見せる（隠しても意味がないため）。
            if hide_hand:
                bench_view = [(m.to_dict() if (m and m.revealed)
                               else ({"hidden": True} if m else None))
                              for m in p.bench]
            else:
                bench_view = [m.to_dict() if m else None for m in p.bench]
            # ベンチの支援カード（指揮官キング・聖女クイーン）による一時バフ。
            # atk_now / def_now には含めず、増分を別に渡して画面で「30(+30)」と出す。
            battle_view = p.battle.to_dict() if p.battle else None
            if battle_view:
                battle_view["atk_buff"] = (AV["C_K_command"]
                                           if p.has_bench_ability("C_K_command") else 0)
                battle_view["def_buff"] = (AV["H_Q_guard"]
                                           if p.has_bench_ability("H_Q_guard") else 0)
            return {
                "name": p.name,
                "is_cpu": p.is_cpu,
                "trainer_hp": p.trainer_hp,
                "trainer_hp_max": p.trainer_hp_max,
                "battle": battle_view,
                "bench": bench_view,
                "hand": ([] if hide_hand else [c.to_dict() for c in p.hand]),
                "hand_count": len(p.hand),
                "monster_hand": ([] if hide_hand else [c.to_dict() for c in p.monster_hand]),
                "monster_hand_count": len(p.monster_hand),
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
            # 自分に見せてよい行だけ残してから最後の60行を渡す。
            # 相手のベンチ・モンスター手札に触れる行はここで落ちる。
            "log": [e.text for e in self.log
                    if e.private_to is None or e.private_to == viewer][-60:],
            "fx": self.fx,
            # まだ攻撃を出せる余地があるか（"now" / "after_swap" / None）。
            # 画面がターン終了の押し忘れを引き止めるのに使う。
            "attack_chance": self.attack_chance(viewer),
            # バトル場の繰り上げを選ぶ番の席（誰も待っていなければ None）
            "pending_promote": self.pending_seat(),
            # めくったカードの選択待ち。候補は本人にしか見せない
            # （相手に見せると山札の中身が漏れてしまう）
            "pending_choice": (
                {"title": self.pending_choice["title"],
                 "picks": self.pending_choice["picks"],
                 "cards": [c.to_dict() for c in self.pending_choice["cards"]]}
                if self.pending_choice and self.pending_choice["seat"] == viewer
                else None),
            "choice_waiting": bool(self.pending_choice),
        }
