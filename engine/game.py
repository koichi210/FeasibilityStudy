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

from .cards import (BALANCE, Card, DEMON_ARMY_KEYS, GOD_ARMY_KEYS,
                    build_item_deck, build_enemy_deck, make_demon_enemy,
                    make_god_enemy, apply_skin)
from .skins import current_skin_id

B = BALANCE
AV = B["ability_values"]
DEMON = B["demon_lord"]
DIVINE = B["divine_army"]
DEMONA = B["demon_army"]
TF = B["third_force"]

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
    "burn": "attack", "poison": "attack", "stun": "attack", "atk_down": "attack",
    "def_down": "attack", "forbidden": "attack", "sacrifice": "attack",
    "atk_down_single": "attack", "atk_down_mutual": "attack",
    "heal": "heal", "full_heal": "heal", "trainer_heal": "heal", "revive": "heal",
    "heal_cure_status": "heal", "heal_self_lock": "heal", "revive_field_fixed_hp": "heal",
    "shield_flat": "buff", "shield_half": "buff",
    "atk_buff_turns": "buff", "def_buff_turns": "buff",
    "weapon_and_atk_down": "buff", "weapon_and_armor": "buff",
    "peek_hand": "buff", "next_move_power": "buff", "peek_reorder_deck": "buff",
    "return_used_item": "buff", "dispel_buff": "buff",
    "weapon_self_cost": "buff", "weapon_armor_self_cost": "buff",
    "weapon_self_defdown": "buff", "armor_self_penalty": "buff",
    "next_move_power_self_cost": "buff", "extra_item_use": "buff",
    "weapon_self_lock": "buff", "weapon_exclude": "buff",
}

# ゲームオプション。新しいゲームを始めるときに指定する。
#   enemy_abilities … J/Q/K/A の特殊能力を使うか。オフだとルールがぐっと単純になる
#   demon_lord        … ♠A の魔王を使うか（技オフのときは自動的にオフ扱い）
DEFAULT_OPTIONS = {
    "enemy_abilities": True,
    "demon_lord": True,
}

OPTION_LABELS = {
    "enemy_abilities": "キャラクターの技",
    "demon_lord": "魔王（♠A）",
}

# _say_hidden / _say_visible / _damage_enemy の actor 引数用の「未指定」印。
# None は「中立（actor=None）を明示的に指定したい」場合と衝突するので、
# デフォルト値には別のセンチネルを使う。
_AUTO_ACTOR = object()


# ==========================================================================
# ログ1行分
# ==========================================================================
@dataclass
class LogEntry:
    """ログ1行。private_to が席番号なら、その人にしか見せない行。

    ベンチとエネミー手札の中身は相手に伏せているので、
    それらのカード名を含む行は private_to 付きで積む。
    view() が viewer ごとに絞ってから返すので、
    通信を覗かれても相手には流れない。
    """
    text: str
    private_to: Optional[int] = None
    # 誰の行動を表す行か。0/1 = プレイヤーの席番号、None = 中立/システムメッセージ
    # （ゲーム開始・ターン区切り・第三勢力の乱入など、どちらのプレイヤーの
    # 「行動」でもない行はNoneのままにする。view() で actor 付きでクライアントへ渡し、
    # 画面側は自分の行動＝白のまま、相手の行動だけ色を付ける）。
    actor: Optional[int] = None

    def __str__(self) -> str:   # simulate.py の print 用
        return self.text


# ==========================================================================
# 場に出ているエネミー1体分の状態
# ==========================================================================
@dataclass
class Enemy:
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
    atk_debuff: int = 0       # atk_down効果でどれだけ攻撃力を下げたか（解除時に戻す用）
    atk_debuff_turns: int = 0  # atk_down効果の残りターン数（0＝かかっていない）
    def_debuff: int = 0       # def_down効果でどれだけ防御力を下げたか（解除時に戻す用）
    def_debuff_turns: int = 0  # def_down効果の残りターン数（0＝かかっていない）
    atk_buff: int = 0         # atk_buff_turns効果でどれだけ攻撃力を上げたか（解除時に戻す用）
    atk_buff_turns: int = 0   # atk_buff_turns効果の残りターン数（0＝かかっていない）
    def_buff: int = 0         # def_buff_turns効果でどれだけ防御力を上げたか（解除時に戻す用）
    def_buff_turns: int = 0   # def_buff_turns効果の残りターン数（0＝かかっていない）
    shield_flat: int = 0      # 次に受けるダメージをこの分だけ軽減する（1回消費で0に戻る）
    shield_half: bool = False  # 次に受けるダメージを半減する（1回消費でFalseに戻る）
    next_attack_bonus: int = 0  # 次の自分の攻撃力に加算する一時修正値（負の値＝次の攻撃だけ弱める）
    attack_locked: bool = False  # 次の自分のターン、攻撃だけできない（交代は可）
    equipment: List[str] = field(default_factory=list)
    revived: bool = False     # 不死鳥を使ったか
    is_demon: bool = False
    demon_turns: int = 0
    ability_enabled: bool = True   # 「技なし」オプション時は False
    bench_turns_left: Optional[int] = None  # 聖女クイーン・指揮官キング専用：
                                             # ベンチにいられる残りターン（None＝対象外）
    is_god_summon: bool = False  # 神軍降臨で召喚された上位互換エネミーか（装備アイテムを使えない）
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
        return self.fatigue <= 0 and not self.attack_locked

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
            "atk_debuff": self.atk_debuff,
            "atk_debuff_turns": self.atk_debuff_turns,
            "def_debuff": self.def_debuff,
            "def_debuff_turns": self.def_debuff_turns,
            "atk_buff": self.atk_buff,
            "atk_buff_turns": self.atk_buff_turns,
            "def_buff": self.def_buff,
            "def_buff_turns": self.def_buff_turns,
            "shield_flat": self.shield_flat,
            "shield_half": self.shield_half,
            "next_attack_bonus": self.next_attack_bonus,
            "attack_locked": self.attack_locked,
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
    battle: Optional[Enemy] = None
    bench: List[Optional[Enemy]] = field(default_factory=list)
    hand: List[Card] = field(default_factory=list)
    enemy_hand: List[Card] = field(default_factory=list)  # 引いたがまだ場に出していないエネミー
    item_used: bool = False
    swaps_left: int = 0
    attacked: bool = False
    # 呪縛：次の自分のターン、攻撃も交代もできない（アイテムだけ使える）。
    # エネミー個体ではなくプレイヤーに掛ける。個体に掛けると
    # ベンチと交代するだけで抜けられてしまうため。
    stunned: bool = False

    def field_enemies(self) -> List[Enemy]:
        out = []
        if self.battle:
            out.append(self.battle)
        out.extend([m for m in self.bench if m])
        return out

    def has_bench_ability(self, ability_id: str) -> bool:
        return any(m and m.ability_id == ability_id for m in self.bench)


# ==========================================================================
# 三つ巴：第三勢力（乱入する中立モンスター）
# ==========================================================================
@dataclass
class ThirdForce:
    """どちらの味方でもない、途中から乱入してくる第三勢力。

    2〜10の数字カードのみで組んだ専用の山札（`deck`）を持つ。
    場に出るのは常に1体だけで、倒されたら山札から次の1体が控えから出てくる。
    山札を出し切って最後の1体まで倒し切ったら、とどめを刺した側の討伐勝利。
    専用ターンは持たず、毎ターン終了時に自動でどちらか一方を1回だけ攻撃する
    （簡易ギミックとして実装。疲労・強制退場などの通常ルールは適用しない）。
    """
    deck: List[Card] = field(default_factory=list)
    discard: List[Card] = field(default_factory=list)
    enemy: Optional[Enemy] = None
    active: bool = False      # 乱入イベントが発生済みか
    defeated: bool = False    # 山札を出し切って討伐が完了したか


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
        if not self.options["enemy_abilities"]:
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
        # 生贄の儀式（weapon_exclude系）で使用されたカードなど、
        # 二度と山札に戻らない「ゲームから除外」されたアイテムの置き場
        self.item_removed: List[Card] = []
        self.third_force = ThirdForce()

    # ---------------------------------------------------------------- setup
    def start(self):
        for p in self.players:
            p.deck = build_enemy_deck()
            self.rng.shuffle(p.deck)
        self.item_deck = build_item_deck()
        self.rng.shuffle(self.item_deck)

        # 三つ巴：第三勢力の専用山札を組む（全スキンの魔神軍6体ずつ = 30体）
        # スキン一覧：arcana, tensura, madomagi, rezero, samurai
        cards = []
        current = current_skin_id()
        for skin_id in ["arcana", "tensura", "madomagi", "rezero", "samurai"]:
            apply_skin(skin_id)
            for key in DEMON_ARMY_KEYS:
                cards.append(make_demon_enemy(key))
        apply_skin(current)  # 元のスキンに戻す
        self.rng.shuffle(cards)
        self.third_force.deck = cards

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

    def _say(self, msg: str, private_to: Optional[int] = None,
             actor: Optional[int] = None):
        """ログを1行足す。

        private_to に席番号を渡すと、その人の画面にだけ出る。
        ベンチ・エネミー手札の中身は相手に伏せているので、
        それらに触れる行は必ず private_to を付けること（付け忘れ＝情報漏洩）。

        actor に席番号を渡すと「誰の行動か」を記録する。画面側はこれを見て
        相手の行動だけ色を付ける。中立の行（システムメッセージ等）は
        actor=None のままでよい。
        """
        self.log.append(LogEntry(msg, private_to, actor))

    def _fx(self, kind: str, attacker: Optional[Enemy] = None,
            target: Optional[Enemy] = None, title: str = "", cry: str = "",
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

    def _say_hidden(self, owner: Player, mine: str, theirs: str,
                     actor: object = _AUTO_ACTOR):
        """伏せてある場所（ベンチ・エネミー手札）の出来事を、見せ方を変えて両者に伝える。

        owner には具体的なカード名入りの `mine` を、相手には
        カード名を伏せた `theirs` を出す。「何かが起きた」ことは伝わるが
        「何のカードか」は漏れない。

        actor を省略すると owner の行動として記録する（多くはこれでよい）。
        第三勢力がらみなど owner の行動と言えない場合だけ、呼び出し側で
        明示的に actor=None（中立）などを渡す。
        """
        if actor is _AUTO_ACTOR:
            actor = owner.idx
        self._say(mine, private_to=owner.idx, actor=actor)
        self._say(theirs, private_to=1 - owner.idx, actor=actor)

    # ------------------------------------------------------------ 山札操作
    def _draw_enemy(self, p: Player) -> Optional[Card]:
        if not p.deck:
            enemies = [c for c in p.discard if c.kind == "enemy"]
            if not enemies:
                return None
            p.discard = [c for c in p.discard if c.kind != "enemy"]
            p.deck = enemies
            self.rng.shuffle(p.deck)
            self._say("♻️ {} の捨て札をシャッフルして山札を再構築".format(p.name), actor=p.idx)
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

    def _spawn(self, p: Player, card: Card) -> Enemy:
        m = Enemy(card=card, uid=self._next_uid(),
                    hp=B["enemy_hp"], hp_max=B["enemy_hp"],
                    base_atk=card.atk, base_def=card.dfn,
                    ability_enabled=self.options["enemy_abilities"])
        if m.ability_id in BENCH_LIMITED_ABILITIES:
            m.bench_turns_left = B["bench_ability_turns"]
        return m

    def _spawn_god(self, p: Player, key: str) -> Enemy:
        """神軍降臨で、J/Q/Kの上位互換エネミーを1体作る。
        技は元のカードと共通（既存ロジックがそのまま効く）。HPだけ通常と異なる。"""
        m = self._spawn(p, make_god_enemy(key))
        m.hp = m.hp_max = DIVINE["hp"]
        m.is_god_summon = True
        return m

    def _spawn_third_force_enemy(self, card: Card) -> Enemy:
        """第三勢力のエネミーを1体作る。J/Q/Kの技は使わない（そもそも2〜10しか入っていない）。"""
        return Enemy(card=card, uid=self._next_uid(),
                     hp=TF["hp"], hp_max=TF["hp"],
                     base_atk=card.atk, base_def=card.dfn,
                     atk_bonus=TF["atk_bonus"], def_bonus=TF["def_bonus"],
                     ability_enabled=False)

    def _activate_third_force(self):
        """第三勢力の乱入イベントを発生させる（1ゲームに1度だけ）。"""
        tf = self.third_force
        tf.active = True
        if not tf.deck:
            return
        card = tf.deck.pop()
        tf.enemy = self._spawn_third_force_enemy(card)
        self._say("🌩️ 第三勢力が乱入してきた！ {} が両陣営に襲いかかる！".format(self._nm(tf.enemy)))
        # target は付けない（登場の合図であって被弾ではないため、爪痕の演出は出さない）
        self._fx("enter", title="🌩️ 第三勢力、乱入！",
                 cry="どちらも滅ぼしてくれる…！", tone="attack")

    def _spawn_demon(self, p: Player, key: str) -> Enemy:
        """魔神軍降臨で、10/9/8の上位互換エネミーを1体作る。
        技は同じスートのJ/Q/Kから借用（既存ロジックがそのまま効く）。HPだけ通常と異なる。"""
        m = self._spawn(p, make_demon_enemy(key))
        m.hp = m.hp_max = DEMONA["hp"]
        return m

    # --------------------------------------------------------------- 場補充
    def _refill_field(self, p: Player, silent: bool = False, instant: bool = False):
        """バトル場の繰り上げを行う（空きがあればベンチから自動で上がる）。

        エネミー手札への補充はここではやらない。アイテム手札と同じく
        `_draw_enemy_to_hand` が自分のターン開始時に1枚だけ引く
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
                    self._say("🔀 {}：ベンチの {} がバトル場へ".format(p.name, self._nm(m)), actor=p.idx)
            elif candidates and self.winner is None:
                if p.idx not in self.pending_promote:
                    self.pending_promote.append(p.idx)
                    # 進行が止まる理由が分からないと不安なので、両者に知らせる。
                    # 何を選んでいるかは伏せたまま「選択中」だけを伝える。
                    if not silent:
                        self._say("🤔 {}：バトル場へ出すカードを選んでいます…".format(p.name), actor=p.idx)
            elif instant:
                card = self._draw_enemy(p)
                if card:
                    self._stand_battle(p, self._spawn(p, card))
                    if not silent:
                        self._say("🆕 {}：バトル場に {} が登場".format(p.name, self._nm(p.battle)), actor=p.idx)
                    self._on_enter(p, p.battle, silent)

        if instant:
            for i in range(len(p.bench)):
                if p.bench[i] is None:
                    card = self._draw_enemy(p)
                    if not card:
                        break
                    p.bench[i] = self._spawn(p, card)
                    if not silent:
                        # ベンチの中身は相手に伏せる
                        self._say_hidden(
                            p,
                            "🆕 {}：ベンチに {} が登場".format(p.name, self._nm(p.bench[i])),
                            "🆕 {}：ベンチにキャラクターが1体登場".format(p.name))
                    self._on_enter(p, p.bench[i], silent)
            return

        # 選ぶ余地が無くなったら待ちを解除する
        # （誰かが出て埋まった／ベンチも全滅して選べるものが無い）
        if p.idx in self.pending_promote and (p.battle is not None or not any(p.bench)):
            self.pending_promote.remove(p.idx)

    def _stand_battle(self, p: Player, m: Optional[Enemy]):
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

    def _draw_enemy_to_hand(self, p: Player, silent: bool = False) -> Optional[Card]:
        """エネミー手札にターン開始時1枚だけ引く（アイテム手札と同じ方式）。

        上限はアイテム手札とは別枠（enemy_hand_size_max）。
        場は4枠しかないので、配置しきれない分を抱えられるよう多めにしてある。
        """
        if len(p.enemy_hand) >= B["enemy_hand_size_max"]:
            return None
        card = self._draw_enemy(p)
        if not card:
            return None
        p.enemy_hand.append(card)
        if not silent:
            # 手札の中身は相手に伏せる（引いた事実だけ伝える）
            self._say_hidden(
                p,
                "🃏 {} が {} をキャラクター手札に加えた".format(
                    p.name, "{}{}".format(card.label, card.name)),
                "🃏 {} がキャラクターを1枚引いた".format(p.name))
        return card

    def _nm(self, m: Enemy) -> str:
        return "魔王" if m.is_demon else "{} {}".format(m.card.label, m.card.name)

    # ----------------------------------------------------------- 登場時効果
    def _on_enter(self, p: Player, m: Enemy, silent: bool = False):
        aid = m.ability_id
        if aid == "S_A_demon" and not self.options["demon_lord"]:
            return  # 魔王なしオプション。♠A はただのカードとして場に残る
        if aid == "S_A_demon":
            m.is_demon = True
            m.hp = m.hp_max = DEMON["hp"]
            m.base_atk = DEMON["atk"]
            m.base_def = DEMON["def"]
            m.demon_turns = DEMON["turns"]
            self._say("👹 {} が魔王を降臨させた！（{}ターンで消滅）".format(p.name, DEMON["turns"]), actor=p.idx)
        elif aid == "H_K_holy":
            v = AV["H_K_trainer_heal"]
            p.trainer_hp = min(p.trainer_hp_max, p.trainer_hp + v)
            self._say("✨ 聖王の加護：{} のトレーナーHPが{}回復".format(p.name, v), actor=p.idx)
        elif aid == "C_Q_scheme":
            for _ in range(AV["C_Q_draw"]):
                self._draw_item(p, silent=True)
            self._say("📜 策謀のクイーン：{} がアイテムを{}枚引いた".format(p.name, AV["C_Q_draw"]), actor=p.idx)
        elif aid == "C_A_sage":
            n = 0
            while len(p.hand) < B["hand_size_max"]:
                if self._draw_item(p, silent=True) is None:
                    break
                n += 1
            self._say("🔮 賢者：{} がアイテムを{}枚補充".format(p.name, n), actor=p.idx)

    # ============================================================ ターン進行
    def _begin_turn(self):
        p = self.players[self.current]
        o = self.players[1 - self.current]
        p.item_used = False
        p.swaps_left = 1
        p.attacked = False
        self._say("──── ターン{}：{} ────".format(self.turn, p.name))

        # 三つ巴：決まったターン数に達したら、第三勢力が乱入する（1ゲームに1度だけ）
        if not self.third_force.active and self.turn >= TF["trigger_turn"]:
            self._activate_third_force()

        # 疲労回復
        for m in p.field_enemies():
            if m.fatigue > 0:
                m.fatigue -= 1

        # 毒・呪いの継続ダメージ
        # 毒＝相手が仕掛けてきたもの→倒れたら相手のせい（トレーナーダメージあり）
        # 呪い＝自分の魔剣の自傷→倒れたら自分のせい（トレーナーダメージなし）
        for m in list(p.field_enemies()):
            if m.poison > 0:
                self._damage_enemy(p, m, m.poison, source="毒", by_opponent=True)
            if m.hp > 0 and m.curse > 0:
                self._damage_enemy(p, m, m.curse, source="呪い", by_opponent=False)

        # atk_down効果（スキン独自効果）のカウントダウン。切れたら元の攻撃力に戻す。
        for m in p.field_enemies():
            if m.atk_debuff_turns > 0:
                m.atk_debuff_turns -= 1
                if m.atk_debuff_turns <= 0 and m.atk_debuff:
                    m.atk_bonus += m.atk_debuff
                    self._say("📈 {} の攻撃力ダウンが切れた".format(self._nm(m)))
                    m.atk_debuff = 0

        # def_down効果（スキン独自効果）のカウントダウン。切れたら元の防御力に戻す。
        for m in p.field_enemies():
            if m.def_debuff_turns > 0:
                m.def_debuff_turns -= 1
                if m.def_debuff_turns <= 0 and m.def_debuff:
                    m.def_bonus += m.def_debuff
                    self._say("🛡️ {} の防御力ダウンが切れた".format(self._nm(m)))
                    m.def_debuff = 0

        # atk_buff_turns効果（スキン独自効果）のカウントダウン。切れたら上げた分を戻す。
        for m in p.field_enemies():
            if m.atk_buff_turns > 0:
                m.atk_buff_turns -= 1
                if m.atk_buff_turns <= 0 and m.atk_buff:
                    m.atk_bonus -= m.atk_buff
                    self._say("📉 {} の攻撃力アップが切れた".format(self._nm(m)))
                    m.atk_buff = 0

        # def_buff_turns効果（スキン独自効果）のカウントダウン。切れたら上げた分を戻す。
        for m in p.field_enemies():
            if m.def_buff_turns > 0:
                m.def_buff_turns -= 1
                if m.def_buff_turns <= 0 and m.def_buff:
                    m.def_bonus -= m.def_buff
                    self._say("📉 {} の防御力アップが切れた".format(self._nm(m)))
                    m.def_buff = 0

        # ターン開始時の技
        for m in p.field_enemies():
            if m.ability_id == "H_J_regen":
                v = AV["H_J_regen"]
                for t in p.field_enemies():
                    t.hp = min(t.hp_max, t.hp + v)
                self._say("💚 ヒーリングナイト：{} の場のキャラクターが{}回復".format(p.name, v))
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
                    # 誰かの操作ではなく自動の期限切れなので中立（actor=None）
                    self._say_hidden(
                        p,
                        "⌛ {} はベンチにいられる期限が切れて退場".format(self._nm(m)),
                        "⌛ {} のベンチのキャラクターが1体、期限切れで退場".format(p.name),
                        actor=None)
                    self._remove(p, m, to_discard=True)

        if self.winner is None:
            self._refill_field(p)
            self._draw_enemy_to_hand(p)
            self._draw_item(p)
        self._check_end()

    def end_turn(self):
        if self.winner is not None:
            return
        # 呪縛は「次の1ターン」だけ。縛られた本人のターンが終わったら解ける。
        self.players[self.current].stunned = False
        # attack_locked（毒の刃・破滅の呪符などの代償）も同じく1ターンだけの効果。
        # 縛られた本人のターンが終わったら解ける。
        if self.players[self.current].battle:
            self.players[self.current].battle.attack_locked = False

        # 三つ巴：第三勢力が場にいれば、ターン終了時に自動で1回だけ襲ってくる
        if self.third_force.enemy is not None:
            self._third_force_attack()
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
                acts.append({"type": "attack", "target": "opponent",
                             "label": "⚔️ 攻撃 → {}".format(target)})
            # 三つ巴：第三勢力が場にいれば、そちらを攻める選択肢も出す
            if self.third_force.enemy is not None:
                acts.append({"type": "attack", "target": "third_force",
                             "label": "🌩️ 攻撃 → 第三勢力 {}".format(
                                 self._nm(self.third_force.enemy))})

        # エネミー配置（手札にいるエネミーを、空いている場に出す）
        for i, c in enumerate(p.enemy_hand):
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

    def _can_attack_with(self, m: Optional[Enemy], o: Player) -> bool:
        """そのエネミーがバトル場にいたとして、いま攻撃できるか。"""
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

    # 「攻撃力/防御力を自分に付与する系」の新type。神軍降臨で召喚された上位互換
    # エネミーは自己バフ全般が使えない、という既存ルール（下のweapon/armor系と同じ）
    # の一貫性を保つため、こちらも p.battle.is_god_summon なら使えない扱いにする。
    SELF_BUFF_TYPES = (
        "weapon_and_atk_down", "weapon_and_armor", "weapon_self_cost",
        "weapon_armor_self_cost", "weapon_self_defdown", "weapon_self_lock",
        "weapon_exclude", "atk_buff_turns", "def_buff_turns", "next_move_power",
        "next_move_power_self_cost", "armor_self_penalty", "atk_down_mutual",
    )

    def _item_usable(self, p: Player, o: Player, c: Card) -> bool:
        t = c.effect.type
        if t in ("heal", "full_heal", "weapon", "armor", "weapon_cursed",
                 "weapon_fragile", "cure_fatigue", "sacrifice"):
            if p.battle is None:
                return False
            # 神軍降臨で召喚された上位互換エネミーは、装備アイテム（武器・防具系のバフ）を使えない
            if t in ("weapon", "armor", "weapon_cursed", "weapon_fragile") \
                    and p.battle.is_god_summon:
                return False
            if t == "cure_fatigue":
                return p.battle.fatigue > 0
            if t in ("heal", "full_heal"):
                return p.battle.hp < p.battle.hp_max
            return True
        if t == "stun":
            return not o.stunned          # 二重掛けは無意味
        if t == "divine_army":
            return p.trainer_hp <= DIVINE["trigger_hp"]
        if t == "demon_army":
            return True  # 魔神軍降臨：いつでも使える
        if t in ("burn", "poison", "atk_down", "def_down", "forbidden"):
            return o.battle is not None
        if t == "summon_god":
            return any(m is None for m in p.bench)
        if t == "trainer_heal":
            return p.trainer_hp < p.trainer_hp_max
        if t == "free_swap":
            return not p.stunned and any(m for m in p.bench)
        if t == "deploy":
            return any(m is None for m in p.bench)
        if t == "draw_items":
            return len(p.hand) < B["hand_size_max"]
        if t == "revive":
            # 戻す先はエネミー手札なので、ベンチの空きではなく手札の空きを見る
            return (any(x.kind == "enemy" for x in p.discard)
                    and len(p.enemy_hand) < B["enemy_hand_size_max"])
        # ---------------------------------------------------------------
        # ここから下は、アルカナスキンの item_effect_overrides で新しく
        # 使われている効果タイプ（2026-09-07 追加）。
        # ---------------------------------------------------------------
        if t in ("heal_cure_status", "shield_flat", "shield_half", "heal_self_lock"):
            return p.battle is not None
        if t in self.SELF_BUFF_TYPES:
            if p.battle is None or p.battle.is_god_summon:
                return False
            if t in ("weapon_and_atk_down", "atk_down_mutual"):
                return o.battle is not None
            return True
        if t == "revive_field_fixed_hp":
            return (any(x.kind == "enemy" for x in p.discard)
                    and any(m is None for m in p.bench))
        if t == "atk_down_single":
            return o.battle is not None
        if t == "peek_hand":
            return len(o.enemy_hand) > 0
        if t == "peek_reorder_deck":
            return len(p.deck) > 0
        if t == "return_used_item":
            return len(self.item_discard) > 0 and len(p.hand) < B["hand_size_max"]
        if t == "dispel_buff":
            return o.battle is not None and (
                o.battle.atk_buff_turns > 0 or o.battle.def_buff_turns > 0)
        if t == "extra_item_use":
            return p.battle is not None and not p.battle.is_god_summon
        return True

    # -------------------------------------------------- めくって選ぶ（アイテム）
    def _begin_choice(self, p: Player, kind: str, title: str,
                      cards: List[Card], picks: int, to: str, hp_fixed: int = None):
        """候補カードを見せて、その中から選んでもらう状態に入る。

        cards はすでに山札／捨て札から取り出してある前提。
        選ばれなかったぶんは `_finish_choice` が元へ戻す。
        CPU は待たせても仕方がないので、その場で自動的に選ぶ。

        to の種類：
          "enemy_hand"     … 選んだ1枚をキャラクター手札へ（既存）
          "hand"           … 選んだ1枚をアイテム手札へ（既存）
          "bench_fixed_hp" … 選んだ1枚を、HP=hp_fixed でベンチの空き枠に直接登場させる
                             （蘇生の秘薬）。残りは捨て札に戻す
          "deck_top"       … 選んだ1枚を山札の一番上に、残りは元の相対順序のまま
                             その下に戻す（絶対障壁）
        """
        if not cards:
            return
        picks = min(picks, len(cards))
        self.pending_choice = {"seat": p.idx, "kind": kind, "title": title,
                               "cards": list(cards), "picks": picks, "to": to,
                               "hp_fixed": hp_fixed}
        if p.is_cpu:
            while self.pending_choice:
                self._do_pick({"index": self._cpu_best_pick()})
            return
        self._say("🤔 {}：{}".format(p.name, title), actor=p.idx)

    def _cpu_best_pick(self) -> int:
        """CPU の選び方。エネミーは強いもの、アイテムは適当に先頭。"""
        cards = self.pending_choice["cards"]
        best, bi = None, 0
        for i, c in enumerate(cards):
            score = c.atk + c.dfn if c.kind == "enemy" else 0
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

        if ch["to"] == "enemy_hand":
            p.enemy_hand.append(card)
            self._say_hidden(
                p,
                "🃏 {} が {}{} を選んだ".format(p.name, card.label, card.name),
                "🃏 {} がキャラクターを1枚選んだ".format(p.name))
        elif ch["to"] == "bench_fixed_hp":
            # 蘇生の秘薬：手札にではなく、ベンチの空き枠に固定HPで直接復活させる
            empty = next((j for j, m in enumerate(p.bench) if m is None), None)
            if empty is None:
                # ベンチが埋まってしまっていたら（理論上は _item_usable で防いでいるはず）
                # 捨て札に戻す
                p.discard.append(card)
                self._say("🚫 蘇生の秘薬：ベンチに空きがなく復活できなかった", actor=p.idx)
            else:
                m = self._spawn(p, card)
                m.hp = m.hp_max = ch["hp_fixed"]
                p.bench[empty] = m
                self._say_hidden(
                    p,
                    "✨ {} が {}{} をHP{}でベンチに復活させた".format(
                        p.name, card.label, card.name, ch["hp_fixed"]),
                    "✨ {} のベンチにキャラクターが1体復活した".format(p.name))
                self._on_enter(p, m)
        elif ch["to"] == "deck_top":
            # 絶対障壁：選んだ1枚は最終的に _finish_choice でまとめて山札の一番上に置く
            # （残りの並び順を保つため、選んだカードだけを先に確保しておく）
            ch["chosen"] = card
            self._say_hidden(
                p,
                "🎴 {} が {}{} を山札の一番上に置いた".format(p.name, card.label, card.name),
                "🎴 {} が山札の並びを入れ替えた".format(p.name))
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
        p = self.players[ch["seat"]]
        rest = ch["cards"]
        if ch["to"] == "deck_top":
            # 選んだ1枚（ch["chosen"]）を一番上に、残り（rest）は元の相対順序のまま
            # その下に戻す。deck は末尾が「山の一番上」（_draw_enemy が pop() する側）。
            chosen = ch.get("chosen")
            if chosen is not None:
                p.deck.extend(reversed(rest))       # 残りを、上→下の順を保ったまま積む
                p.deck.append(chosen)               # 選んだ1枚を最後に積んで一番上にする
            elif rest:
                p.deck.extend(reversed(rest))
            return
        if not rest:
            return
        if ch["kind"] == "revive" or ch["to"] == "bench_fixed_hp":
            p.discard.extend(rest)              # 捨て札はそのまま戻す
        elif ch["kind"] == "return_used_item":
            self.item_discard.extend(rest)      # 気付け薬：選ばれなかった分はそのまま捨て札に残す
        elif ch["to"] == "enemy_hand":
            p.deck.extend(rest)                 # 山札へ戻して混ぜる
            self.rng.shuffle(p.deck)
        else:
            self.item_deck.extend(rest)
            self.rng.shuffle(self.item_deck)

    def _do_promote(self, action: dict) -> bool:
        """空いたバトル場に、選ばれたベンチのエネミーを繰り上げる。"""
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
        self._say("🔀 {}：ベンチの {} をバトル場へ出した".format(p.name, self._nm(m)), actor=p.idx)
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
            if action.get("target") == "third_force":
                if self.third_force.enemy is None:
                    return False
                self._do_attack_third_force(p)
            else:
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
            self._say("🔄 {}：{} と交代".format(p.name, self._nm(p.battle)), actor=p.idx)
        elif t == "place":
            i = action.get("hand", -1)
            slot = action.get("slot")
            if not (0 <= i < len(p.enemy_hand)):
                return False
            if slot == "battle":
                if p.battle is not None:
                    return False
                card = p.enemy_hand.pop(i)
                self._stand_battle(p, self._spawn(p, card))
                self._say("🆕 {}：バトル場に {} が登場".format(p.name, self._nm(p.battle)), actor=p.idx)
                self._on_enter(p, p.battle)
            elif isinstance(slot, int) and 0 <= slot < len(p.bench) and p.bench[slot] is None:
                card = p.enemy_hand.pop(i)
                p.bench[slot] = self._spawn(p, card)
                # ベンチは伏せ札なので、相手にはカード名を出さない
                self._say_hidden(
                    p,
                    "🆕 {}：ベンチに {} が登場".format(p.name, self._nm(p.bench[slot])),
                    "🆕 {}：ベンチにキャラクターを1体配置".format(p.name))
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
    def _effective_atk(self, p: Player, m: Enemy) -> int:
        v = m.base_atk + m.atk_bonus + m.next_attack_bonus
        if p.has_bench_ability("C_K_command"):
            v += AV["C_K_command"]
        return v

    def _effective_def(self, p: Player, m: Enemy) -> int:
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
        self._say("🗣️ {}「{}」".format(p.name, cry), actor=p.idx)

        # 直接攻撃（相手の場が空）
        if o.battle is None:
            if aid == "S_J_reckless":
                atk += AV["S_J_reckless_bonus"]
            o.trainer_hp -= atk
            self._say("💥 {} の {} が直接攻撃！{} のトレーナーに{}ダメージ".format(
                p.name, self._nm(a), o.name, atk), actor=p.idx)
        else:
            d = o.battle
            dfn = self._effective_def(o, d)
            if aid == "D_Q_pierce":
                dfn = int(dfn * AV["D_Q_pierce_rate"])
                self._say("🗡️ ピアススピア：相手の防御を{}%として計算".format(
                    int(AV["D_Q_pierce_rate"] * 100)), actor=p.idx)
            if aid == "S_J_reckless":
                atk += AV["S_J_reckless_bonus"]
            dmg = max(B["min_damage"], atk - dfn)
            self._say("⚔️ {} の {}（攻{}）→ {} の {}（防{}）に {}ダメージ".format(
                p.name, self._nm(a), atk, o.name, self._nm(d), dfn, dmg), actor=p.idx)

            # 攻撃時の追加効果
            if aid == "D_K_destroyer":
                v = AV["D_K_trainer_damage"]
                o.trainer_hp -= v
                self._say("💀 破壊王：{} のトレーナーにも{}ダメージ".format(o.name, v), actor=p.idx)
            if aid == "S_Q_poison":
                d.poison = max(d.poison, AV["S_Q_poison"])
                self._say("☠️ ポイズンクイーン：{} が毒状態に".format(self._nm(d)), actor=p.idx)
            if aid == "C_J_disturb":
                d.fatigue = max(d.fatigue, B["fatigue_turns"])
                self._say("🌀 トリックスター：{} を疲労させた".format(self._nm(d)), actor=p.idx)
            if aid == "D_J_splash":
                v = AV["D_J_splash"]
                for bm in [m for m in o.bench if m]:
                    self._damage_enemy(o, bm, v, source="デュアルブレイド", by_opponent=True)
                self._say("🌪️ デュアルブレイド：相手ベンチ全体に{}ダメージ".format(v), actor=p.idx)
            if aid == "S_A_demon" and a.is_demon and DEMON.get("splash", 0) > 0:
                v = DEMON["splash"]
                for bm in [m for m in o.bench if m]:
                    self._damage_enemy(o, bm, v, source="多重展開", by_opponent=True)
                self._say("🟢 多重展開（マルチプル）：相手ベンチ全体に{}ダメージ".format(v), actor=p.idx)

            self._damage_enemy(o, d, dmg, source="攻撃", by_opponent=True)

        # 反動ダメージ
        if aid == "S_J_reckless":
            self._damage_enemy(p, a, AV["S_J_reckless_recoil"], source="反動", by_opponent=False)
        if aid == "S_K_tyrant":
            self._damage_enemy(p, a, AV["S_K_tyrant_recoil"], source="暴君の代償", by_opponent=False)

        if p.battle is not a:  # 反動で自滅した
            return

        self._post_attack_upkeep(p, a, aid)

    def _post_attack_upkeep(self, p: Player, a: Enemy, aid: Optional[str]):
        """攻撃したあとの後始末（魔王のカウント・伝説の剣・疲労・強制退場）。

        通常の対戦相手への攻撃（`_do_attack`）と第三勢力への攻撃
        （`_do_attack_third_force`）の両方から呼ばれる共通処理。
        """
        # 魔王は攻撃してもカウントが進む。
        # 「攻撃 → ベンチへ退避」を繰り返すとターン開始時のカウントを踏まず、
        # 実質いつまでも居座れてしまう抜け穴があったため。
        if a.is_demon and a.demon_turns > 0:
            a.demon_turns -= 1
            if a.demon_turns <= 0:
                self._say("👹 {} の魔王が力を使い果たして消滅した".format(p.name), actor=p.idx)
                self._remove(p, a, to_discard=True)
                return

        # 伝説の剣は1回で壊れる
        if a.fragile_atk:
            a.atk_bonus -= a.fragile_atk
            a.fragile_atk = 0
            if "伝説の剣" in a.equipment:
                a.equipment.remove("伝説の剣")
            self._say("💔 伝説の剣が砕け散った", actor=p.idx)

        # 次の攻撃だけの一時修正値（技の威力アップ／相手からの弱体化）は、
        # 1回攻撃したらリセットする
        a.next_attack_bonus = 0

        # 疲労と強制退場
        a.attacks_used += 1
        if aid == "D_A_onehit":
            self._say("☄️ 一撃必殺：{} は役目を終えて退場".format(self._nm(a)), actor=p.idx)
            self._remove(p, a, to_discard=True)
            return
        if aid != "S_K_tyrant":
            a.fatigue = B["fatigue_turns"]
            self._say("😴 {} は疲労した".format(self._nm(a)), actor=p.idx)
        else:
            self._say("👑 暴君は疲労しない", actor=p.idx)

        if a.attacks_used >= B["attacks_before_retire"]:
            self._say("🚪 {} は{}回攻撃したので強制退場".format(self._nm(a), a.attacks_used), actor=p.idx)
            self._remove(p, a, to_discard=True)

    # ---------------------------------------------------- 三つ巴：第三勢力戦
    def _do_attack_third_force(self, p: Player):
        """自分のバトル場のエネミーで、第三勢力を攻撃する。

        トレーナー絡みの技（破壊王・ポイズンクイーンなど）は第三勢力には
        効果が薄い（トレーナーもベンチも持たない相手）ため対象外にしてある。
        無謀の型・ピアススピアなど、単純にダメージ計算へ絡む技だけ効かせる。
        """
        a = p.battle
        p.attacked = True
        tf = self.third_force
        d = tf.enemy
        atk = self._effective_atk(p, a)
        aid = a.ability_id
        cry = "いけっ、{}！".format(a.card.name if not a.is_demon else "魔王")
        self._fx("attack", attacker=a, target=d,
                 title="⚔️ {} の こうげき".format(self._nm(a)), cry=cry, tone="attack")
        self._say("🗣️ {}「{}」".format(p.name, cry), actor=p.idx)

        dfn = d.base_def + d.def_bonus
        if aid == "D_Q_pierce":
            dfn = int(dfn * AV["D_Q_pierce_rate"])
            self._say("🗡️ ピアススピア：第三勢力の防御を{}%として計算".format(
                int(AV["D_Q_pierce_rate"] * 100)), actor=p.idx)
        if aid == "S_J_reckless":
            atk += AV["S_J_reckless_bonus"]
        dmg = max(B["min_damage"], atk - dfn)
        self._say("⚔️ {} の {}（攻{}）→ 第三勢力 {}（防{}）に {}ダメージ".format(
            p.name, self._nm(a), atk, self._nm(d), dfn, dmg), actor=p.idx)
        self._damage_third_force(p, dmg)

        # 反動ダメージ
        if aid == "S_J_reckless":
            self._damage_enemy(p, a, AV["S_J_reckless_recoil"], source="反動", by_opponent=False)
        if aid == "S_K_tyrant":
            self._damage_enemy(p, a, AV["S_K_tyrant_recoil"], source="暴君の代償", by_opponent=False)

        if p.battle is not a:  # 反動で自滅した
            return
        self._post_attack_upkeep(p, a, aid)

    def _damage_third_force(self, p: Player, dmg: int):
        """第三勢力にダメージを与える。倒したら山札から次の1体が倒したプレイヤーのベンチに配置される。

        山札を出し切って最後の1体まで倒し切ったら、とどめを刺した p の討伐勝利。
        """
        tf = self.third_force
        m = tf.enemy
        if m is None or dmg <= 0:
            return
        m.hp -= dmg
        if m.hp > 0:
            return
        # 第三勢力を倒したのは p の行動（攻撃）の結果なので actor=p.idx
        self._say("☠️ 第三勢力の {} が倒れた！".format(self._nm(m)), actor=p.idx)
        tf.discard.append(m.card)
        tf.enemy = None
        if tf.deck:
            card = tf.deck.pop()
            # ベンチに空きがあるか確認して配置
            placed = False
            for i in range(len(p.bench)):
                if p.bench[i] is None:
                    e = self._spawn_third_force_enemy(card)
                    p.bench[i] = e
                    self._say("🎖️ {} が {} のベンチスロット {} に配置された！（残り{}体）".format(
                        self._nm(e), p.name, i + 1, len(tf.deck)), actor=p.idx)
                    placed = True
                    break
            if not placed:
                # ベンチが満杯なら手札に追加。
                # ⚠️ enemy_hand は Card のリスト（まだ場に出していない札）。
                # Enemy（第三勢力用に強化済みのインスタンス）をそのまま入れると
                # 型が合わず、legal_actions() で c.label 参照時に落ちる
                # （2026-09-12 発覚：ベンチ満杯時に third_force 報酬を受け取ると
                #  以後の合法手一覧生成でクラッシュしていたバグ）。
                # 手札に戻す以上は「まだ場に出ていない札」に過ぎないので、
                # 第三勢力用の強化ステータス（HP/攻防ボーナス）は場に出す
                # （_spawn_third_force_enemy を呼ぶ）タイミングまで持ち越さず、
                # 素の card のまま持たせる。
                p.enemy_hand.append(card)
                self._say("📥 {}{} が {} のキャラクター手札に追加された！（残り{}体）".format(
                    card.label, card.name, p.name, len(tf.deck)), actor=p.idx)
        else:
            tf.defeated = True
            self.winner = p.idx
            self.finish_reason = "第三勢力を討伐した"
            self._say("🏆 {} が第三勢力を討伐した！{} の勝ち！".format(p.name, p.name))

    def _third_force_attack(self):
        """第三勢力の自動行動。ターン終了時に、どちらか一方を1回だけ襲う。

        専用ターンは持たないので、疲労や強制退場のような通常ルールは適用しない
        （簡易ギミックとしての実装）。
        """
        tf = self.third_force
        m = tf.enemy
        if m is None:
            return
        seat = self.rng.randrange(2)
        target = self.players[seat]
        atk = m.base_atk + m.atk_bonus
        self._fx("attack", attacker=m, target=target.battle,
                 title="🌩️ 第三勢力の 強襲", cry="邪魔者は消える！", tone="attack")
        self._say("🌩️ 第三勢力が {} を強襲！".format(target.name))
        if target.battle is None:
            target.trainer_hp -= atk
            self._say("💥 第三勢力の攻撃が直撃！{} のトレーナーに{}ダメージ".format(
                target.name, atk))
        else:
            d = target.battle
            dfn = self._effective_def(target, d)
            dmg = max(B["min_damage"], atk - dfn)
            self._say("⚔️ 第三勢力の攻撃（攻{}）→ {} の {}（防{}）に {}ダメージ".format(
                atk, target.name, self._nm(d), dfn, dmg))
            # 第三勢力はどちらのプレイヤーでもないので中立扱い（actor=None）
            self._damage_enemy(target, d, dmg, source="第三勢力", by_opponent=True,
                                actor=None)
        self._check_end()

    # ------------------------------------------------------ ダメージ／退場
    def _damage_enemy(self, owner: Player, m: Enemy, dmg: int,
                        source: str = "", by_opponent: bool = True,
                        actor: object = _AUTO_ACTOR):
        if dmg <= 0 or m.hp <= 0:
            return
        # actor省略時：by_opponent=True なら「相手がやった」ので相手の席番号、
        # False なら「自分自身の行動（反動・代償など）」なので owner 自身。
        # 第三勢力がらみのダメージ（相手プレイヤーの仕業ではない）は、呼び出し側で
        # actor=None を明示して中立扱いにする。
        if actor is _AUTO_ACTOR:
            actor = (1 - owner.idx) if by_opponent else owner.idx
        # シールド系（応急処置・白銀の秘薬など）の消費処理。
        # flat軽減を先に適用し、残りを半減する（両方セットされていた場合の順序）。
        if m.shield_flat > 0:
            reduced = min(m.shield_flat, dmg)
            dmg -= reduced
            m.shield_flat = 0
            self._say_visible(
                owner, m,
                "🛡️ {} がシールドで{}ダメージ軽減".format(self._nm(m), reduced),
                "🛡️ {} のベンチのキャラクターがシールドでダメージ軽減".format(owner.name),
                actor=actor)
        if m.shield_half:
            dmg = dmg // 2
            m.shield_half = False
            self._say_visible(
                owner, m,
                "🛡️ {} がシールドでダメージ半減".format(self._nm(m)),
                "🛡️ {} のベンチのキャラクターがシールドでダメージ半減".format(owner.name),
                actor=actor)
        if dmg <= 0:
            return
        m.hp -= dmg
        if source in ("毒", "呪い"):
            self._say_visible(
                owner, m,
                "🩸 {} の {} が{}の継続ダメージで{}ダメージ".format(
                    owner.name, self._nm(m), source, dmg),
                "🩸 {} のベンチのキャラクターが{}の継続ダメージで{}ダメージ".format(
                    owner.name, source, dmg),
                actor=actor)
        if m.hp <= 0:
            self._defeat(owner, m, by_opponent, actor=actor)

    def _say_visible(self, owner: Player, m: Enemy, mine: str, theirs: str,
                      actor: object = _AUTO_ACTOR):
        """エネミーの居場所に応じてログの見せ方を切り替える。

        バトル場は公開情報なのでそのまま全員に出す。
        ベンチは伏せ札なので、相手にはカード名を伏せた `theirs` を出す。
        """
        if actor is _AUTO_ACTOR:
            actor = owner.idx
        if owner.battle is m:
            self._say(mine, actor=actor)
        else:
            self._say_hidden(owner, mine, theirs, actor=actor)

    def _defeat(self, owner: Player, m: Enemy, by_opponent: bool,
                actor: object = _AUTO_ACTOR):
        if actor is _AUTO_ACTOR:
            actor = (1 - owner.idx) if by_opponent else owner.idx
        # 不死鳥：1度だけ全快で復活
        if m.ability_id == "H_A_phoenix" and not m.revived:
            m.revived = True
            m.hp = m.hp_max
            m.poison = 0
            self._say_visible(
                owner, m,
                "🔥 不死鳥が蘇った！{} はHP全快で復活".format(self._nm(m)),
                "🔥 {} のベンチで不死鳥が蘇った".format(owner.name),
                actor=actor)
            return
        self._say_visible(
            owner, m,
            "☠️ {} の {} が倒れた".format(owner.name, self._nm(m)),
            "☠️ {} のベンチのキャラクターが1体倒れた".format(owner.name),
            actor=actor)
        # 撃破ダメージは「倒れた」の直後に出す。
        # 先に _remove すると、そこから出る繰り上げの案内が間に割り込んでしまう。
        if by_opponent:
            v = B["kill_trainer_damage"]
            owner.trainer_hp -= v
            self._say("💢 {} のトレーナーに{}ダメージ".format(owner.name, v), actor=actor)
        self._remove(owner, m, to_discard=True)

    def _remove(self, owner: Player, m: Enemy, to_discard: bool = True):
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
        self._say("🎒 {} が「{}」を使用".format(p.name, c.name), actor=p.idx)
        if e.cry:
            self._say("🗣️ {}「{}」".format(p.name, e.cry), actor=p.idx)
        # 画面中央に大きく出す。色は効果の性質で分ける（赤=攻め / 緑=癒し / 青=強化）
        self._fx("item", title="🎒 {}".format(c.name), cry=e.cry,
                 tone=ITEM_TONE.get(t, "buff"))

        if t == "heal":
            p.battle.hp = min(p.battle.hp_max, p.battle.hp + v)
            self._say("💚 {} のHPが{}回復（{}/{}）".format(
                self._nm(p.battle), v, p.battle.hp, p.battle.hp_max), actor=p.idx)
        elif t == "full_heal":
            p.battle.hp = p.battle.hp_max
            p.battle.poison = 0
            self._say("💚 {} のHPが全回復".format(self._nm(p.battle)), actor=p.idx)
        elif t == "trainer_heal":
            p.trainer_hp = min(p.trainer_hp_max, p.trainer_hp + v)
            self._say("✨ トレーナーHPが{}回復（{}）".format(v, p.trainer_hp), actor=p.idx)
        elif t == "weapon":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v), actor=p.idx)
        elif t == "armor":
            p.battle.def_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🛡️ {} の防御+{}".format(self._nm(p.battle), v), actor=p.idx)
        elif t == "weapon_cursed":
            p.battle.atk_bonus += v
            p.battle.curse += e.extra
            p.battle.equipment.append("魔剣(+{})".format(v))
            self._say("🗡️ {} の攻撃+{}（毎ターン{}の自傷）".format(self._nm(p.battle), v, e.extra), actor=p.idx)
        elif t == "weapon_fragile":
            p.battle.atk_bonus += v
            p.battle.fragile_atk += v
            p.battle.equipment.append("伝説の剣")
            self._say("⚔️ {} の攻撃+{}（1回攻撃で壊れる）".format(self._nm(p.battle), v), actor=p.idx)
        elif t == "burn":
            self._say("🔥 {} に{}ダメージ".format(self._nm(o.battle), v), actor=p.idx)
            # 直前のアイテム演出に、被弾の相手を書き足す（別の演出にはしない）
            if self.fx:
                self.fx["target"] = o.battle.uid
            self._damage_enemy(o, o.battle, v, source="呪符", by_opponent=True)
            if e.extra and p.battle:
                self._say("🩸 反動で自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra), actor=p.idx)
                self._damage_enemy(p, p.battle, e.extra, source="反動", by_opponent=False)
        elif t == "poison":
            o.battle.poison = max(o.battle.poison, v)
            self._say("☠️ {} が毒状態に（毎ターン{}）".format(self._nm(o.battle), v), actor=p.idx)
        elif t == "atk_down":
            # スキン独自効果（例：転スラの「暴食者」）。相手のバトル場の攻撃力を
            # 一定ターンの間だけ下げる。二重掛けはターン数を上書きするだけ
            # （デバフ量は重ねない＝下がりすぎ防止）。
            target = o.battle
            if target.atk_debuff_turns <= 0:
                target.atk_bonus -= v
                target.atk_debuff = v
            target.atk_debuff_turns = max(target.atk_debuff_turns, e.extra)
            self._say("📉 {} の攻撃力が{}ターンの間 -{}".format(self._nm(target), e.extra, v), actor=p.idx)
        elif t == "def_down":
            # atk_down と対の、スキン独自効果（例：まどマギの「呪詛」系アイテム）。
            # 相手のバトル場の防御力を一定ターンの間だけ下げる。仕組みはatk_downと同じ。
            target = o.battle
            if target.def_debuff_turns <= 0:
                target.def_bonus -= v
                target.def_debuff = v
            target.def_debuff_turns = max(target.def_debuff_turns, e.extra)
            self._say("📉 {} の防御力が{}ターンの間 -{}".format(self._nm(target), e.extra, v), actor=p.idx)
        elif t == "stun":
            # エネミーではなくプレイヤーを縛る。交代で逃げられないように。
            o.stunned = True
            self._say("🌀 {} は次のターン、攻撃も交代もできない".format(o.name), actor=p.idx)
        elif t == "cure_fatigue":
            p.battle.fatigue = 0
            self._say("⚡ {} の疲労が回復".format(self._nm(p.battle)), actor=p.idx)
        elif t == "free_swap":
            p.swaps_left += 1
            self._say("🔄 交代権を1回追加", actor=p.idx)
        elif t == "deploy":
            # 山札の上から数枚めくって、その中から選ぶ。
            # 山札全部から選べると欲しいカードが必ず来てしまうので、候補を絞る。
            if len(p.enemy_hand) >= B["enemy_hand_size_max"]:
                self._say("🚫 号令：キャラクター手札が上限で追加できなかった", actor=p.idx)
            else:
                look = [c for c in (self._draw_enemy(p)
                                    for _ in range(B["look_at_cards"])) if c]
                self._begin_choice(p, "deploy",
                                   "号令：めくった{}枚から1枚選ぶ".format(len(look)),
                                   look, 1, "enemy_hand")
        elif t == "divine_army":
            # 代償：自分のトレーナーHPを削る（自滅しても構わない禁忌の力という位置づけ）
            cost = DIVINE["cost_hp"]
            p.trainer_hp -= cost
            self._say("🩸 代償：{} のトレーナーHP-{}（残り{}）".format(p.name, cost, p.trainer_hp), actor=p.idx)

            # ベンチのエネミーは失われない。エネミー手札に戻して温存する
            # （収まりきらない分だけ、やむを得ず捨て札へ）
            returned = []
            for i, m in enumerate(p.bench):
                if m:
                    p.bench[i] = None
                    returned.append(m.card)
            room = max(0, B["enemy_hand_size_max"] - len(p.enemy_hand))
            p.enemy_hand.extend(returned[:room])
            overflow = returned[room:]
            if overflow:
                p.discard.extend(overflow)
            if returned:
                self._say_hidden(
                    p,
                    "🌀 ベンチのキャラクターが手札に戻った（{}）".format(
                        "・".join(c.label + c.name for c in returned)),
                    "🌀 {} のベンチのキャラクターが手札に戻った".format(p.name))

            # 神々を3体、ランダムにベンチへ直接召喚する
            picks = self.rng.sample(GOD_ARMY_KEYS, min(3, len(GOD_ARMY_KEYS), len(p.bench)))
            for i, key in enumerate(picks):
                god = self._spawn_god(p, key)
                p.bench[i] = god
                self._say_hidden(
                    p,
                    "✨ {} が降臨した！".format(self._nm(god)),
                    "✨ {} のベンチに何かが降臨した…！".format(p.name))
                self._on_enter(p, god)
        elif t == "demon_army":
            # 代償：自分のトレーナーHPを削る（禁忌の力という位置づけは神軍降臨と同じ）
            cost = DEMONA["cost_hp"]
            p.trainer_hp -= cost
            self._say("🩸 代償：{} のトレーナーHP-{}（残り{}）".format(p.name, cost, p.trainer_hp), actor=p.idx)

            # ベンチのエネミーは失われない。エネミー手札に戻して温存する
            returned = []
            for i, m in enumerate(p.bench):
                if m:
                    p.bench[i] = None
                    returned.append(m.card)
            room = max(0, B["enemy_hand_size_max"] - len(p.enemy_hand))
            p.enemy_hand.extend(returned[:room])
            overflow = returned[room:]
            if overflow:
                p.discard.extend(overflow)
            if returned:
                self._say_hidden(
                    p,
                    "🌀 ベンチのキャラクターが手札に戻った（{}）".format(
                        "・".join(c.label + c.name for c in returned)),
                    "🌀 {} のベンチのキャラクターが手札に戻った".format(p.name))

            # 魔神を3体、ランダムにベンチへ直接召喚する
            picks = self.rng.sample(DEMON_ARMY_KEYS, min(3, len(DEMON_ARMY_KEYS), len(p.bench)))
            for i, key in enumerate(picks):
                demon = self._spawn_demon(p, key)
                p.bench[i] = demon
                self._say_hidden(
                    p,
                    "✨ {} が降臨した！".format(self._nm(demon)),
                    "✨ {} のベンチに何かが降臨した…！".format(p.name))
                self._on_enter(p, demon)
        elif t == "summon_god":
            # スキン独自効果（例：転スラの「神域結界」）。神軍降臨(divine_army)と違い
            # コストも発動条件もなく、ベンチの空き1枠に魔王クラスを1体だけ呼び出す
            # 軽量版。既存のベンチのエネミーは失われない（空き枠に置くだけ）。
            empty = next((i for i, m in enumerate(p.bench) if m is None), None)
            if empty is None:
                self._say("🚫 ベンチに空きがなく召喚できなかった", actor=p.idx)
            else:
                key = self.rng.choice(GOD_ARMY_KEYS)
                god = self._spawn_god(p, key)
                p.bench[empty] = god
                self._say_hidden(
                    p,
                    "✨ {} が降臨した！".format(self._nm(god)),
                    "✨ {} のベンチに何かが降臨した…！".format(p.name))
                self._on_enter(p, god)
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
            if len(p.enemy_hand) >= B["enemy_hand_size_max"]:
                self._say("🚫 蘇生：キャラクター手札が上限で戻せなかった", actor=p.idx)
            else:
                enemies = [x for x in p.discard if x.kind == "enemy"]
                for x in enemies:
                    p.discard.remove(x)
                self._begin_choice(p, "revive", "蘇生：捨て札から1枚選ぶ",
                                   enemies, 1, "enemy_hand")
        elif t == "sacrifice":
            target = p.battle
            self._say("🩸 生贄の儀式：{} を捧げた".format(self._nm(target)), actor=p.idx)
            self._remove(p, target, to_discard=True)
            o.trainer_hp -= v
            self._say("💢 {} のトレーナーに{}ダメージ".format(o.name, v), actor=p.idx)
        elif t == "forbidden":
            p.trainer_hp -= v
            self._say("🕯️ 禁断の契約：自分のトレーナーHP-{}".format(v), actor=p.idx)
            target = o.battle
            if target:
                # 相手のエネミーを葬った扱い。倒したのはこちらなので
                # 相手トレーナーにも撃破ダメージが入る（_remove では入らない）
                self._say("🌑 {} を葬り去った".format(self._nm(target)), actor=p.idx)
                self._defeat(o, target, by_opponent=True)
        # ---------------------------------------------------------------
        # ここから下は、アルカナスキンの item_effect_overrides で新しく
        # 使われている効果タイプ（2026-09-07 追加）。
        # ---------------------------------------------------------------
        elif t == "heal_cure_status":
            # heal と同じ回復に加え、状態異常（毒・攻撃力/防御力ダウン）を治す
            p.battle.hp = min(p.battle.hp_max, p.battle.hp + v)
            p.battle.poison = 0
            if p.battle.atk_debuff_turns > 0 and p.battle.atk_debuff:
                p.battle.atk_bonus += p.battle.atk_debuff
                p.battle.atk_debuff = 0
                p.battle.atk_debuff_turns = 0
            if p.battle.def_debuff_turns > 0 and p.battle.def_debuff:
                p.battle.def_bonus += p.battle.def_debuff
                p.battle.def_debuff = 0
                p.battle.def_debuff_turns = 0
            self._say("💚 {} のHPが{}回復し、状態異常が治った（{}/{}）".format(
                self._nm(p.battle), v, p.battle.hp, p.battle.hp_max), actor=p.idx)
        elif t == "shield_flat":
            p.battle.shield_flat = v
            self._say("🛡️ {} は次に受けるダメージを{}軽減する".format(self._nm(p.battle), v), actor=p.idx)
        elif t == "shield_half":
            p.battle.shield_half = True
            self._say("🛡️ {} は次に受けるダメージを半減する".format(self._nm(p.battle)), actor=p.idx)
        elif t == "def_buff_turns":
            # atk_down の防御・正版。二重掛けはターン上書きのみ（量は重ねない）
            target = p.battle
            if target.def_buff_turns <= 0:
                target.def_bonus += v
                target.def_buff = v
            target.def_buff_turns = max(target.def_buff_turns, e.extra)
            self._say("📈 {} の防御力が{}ターンの間 +{}".format(self._nm(target), e.extra, v), actor=p.idx)
        elif t == "atk_buff_turns":
            target = p.battle
            if target.atk_buff_turns <= 0:
                target.atk_bonus += v
                target.atk_buff = v
            target.atk_buff_turns = max(target.atk_buff_turns, e.extra)
            self._say("📈 {} の攻撃力が{}ターンの間 +{}".format(self._nm(target), e.extra, v), actor=p.idx)
        elif t == "revive_field_fixed_hp":
            # 捨て札からエネミーを1体選ばせ、手札を経由せずベンチへ直接
            # HP固定で復活させる（蘇生の秘薬）
            if not any(m is None for m in p.bench):
                self._say("🚫 蘇生の秘薬：ベンチに空きがなく復活できなかった", actor=p.idx)
            else:
                enemies = [x for x in p.discard if x.kind == "enemy"]
                for x in enemies:
                    p.discard.remove(x)
                self._begin_choice(p, "revive",
                                   "蘇生の秘薬：捨て札から1枚選んでHP{}で復活".format(v),
                                   enemies, 1, "bench_fixed_hp", hp_fixed=v)
        elif t == "weapon_and_atk_down":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v), actor=p.idx)
            target = o.battle
            if target.atk_debuff_turns <= 0:
                target.atk_bonus -= e.extra
                target.atk_debuff = e.extra
            target.atk_debuff_turns = max(target.atk_debuff_turns, 2)
            self._say("📉 {} の攻撃力が2ターンの間 -{}".format(self._nm(target), e.extra), actor=p.idx)
        elif t == "atk_down_single":
            # ターン経過に関係なく、相手が次に1回攻撃するときだけ弱める
            o.battle.next_attack_bonus -= v
            self._say("📉 {} の次の攻撃力が-{}".format(self._nm(o.battle), v), actor=p.idx)
        elif t == "peek_hand":
            if not o.enemy_hand:
                self._say_hidden(
                    p, "👀 相手のキャラクター手札は0枚だった",
                    "👀 {} に手札を覗かれた（何も無かった）".format(p.name))
            else:
                seen = self.rng.choice(o.enemy_hand)
                self._say_hidden(
                    p,
                    "👀 {} の手札を覗いた：{}{}".format(o.name, seen.label, seen.name),
                    "👀 {} に手札を覗かれた".format(p.name))
        elif t == "next_move_power":
            p.battle.next_attack_bonus += v
            self._say("💪 {} の次の技の威力+{}".format(self._nm(p.battle), v), actor=p.idx)
        elif t == "peek_reorder_deck":
            look = []
            for _ in range(min(3, len(p.deck))):
                look.append(p.deck.pop())
            if not look:
                self._say("🚫 絶対障壁：山札が空で並べ替えられなかった", actor=p.idx)
            else:
                self._begin_choice(p, "deck_top",
                                   "絶対障壁：山札の上から{}枚を見て、1枚を一番上に置く".format(len(look)),
                                   look, 1, "deck_top")
        elif t == "weapon_and_armor":
            p.battle.atk_bonus += v
            p.battle.def_bonus += e.extra
            p.battle.equipment.append("{}(攻+{})".format(c.name, v))
            p.battle.equipment.append("{}(防+{})".format(c.name, e.extra))
            self._say("🗡️🛡️ {} の攻撃+{}・防御+{}".format(self._nm(p.battle), v, e.extra), actor=p.idx)
        elif t == "return_used_item":
            if not self.item_discard:
                self._say("🚫 気付け薬：捨て札にアイテムが無かった", actor=p.idx)
            else:
                look = list(self.item_discard)
                self.item_discard = []
                self._begin_choice(p, "return_used_item",
                                   "気付け薬：使ったアイテムを1枚、捨て札から手札に戻す",
                                   look, 1, "hand")
        elif t == "dispel_buff":
            target = o.battle
            if target.atk_buff_turns > 0:
                target.atk_bonus -= target.atk_buff
                target.atk_buff = 0
                target.atk_buff_turns = 0
                self._say("🌀 入れ替え：{} の攻撃力アップを打ち消した".format(self._nm(target)), actor=p.idx)
            elif target.def_buff_turns > 0:
                target.def_bonus -= target.def_buff
                target.def_buff = 0
                target.def_buff_turns = 0
                self._say("🌀 入れ替え：{} の防御力アップを打ち消した".format(self._nm(target)), actor=p.idx)
            else:
                self._say("🌀 入れ替え：打ち消すバフが無かった", actor=p.idx)
        elif t == "weapon_self_cost":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v), actor=p.idx)
            self._say("🩸 代償：自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra), actor=p.idx)
            self._damage_enemy(p, p.battle, e.extra, source="禁術の代償", by_opponent=False)
        elif t == "weapon_armor_self_cost":
            p.battle.atk_bonus += v
            p.battle.def_bonus += e.extra
            p.battle.equipment.append("{}(攻+{})".format(c.name, v))
            p.battle.equipment.append("{}(防+{})".format(c.name, e.extra))
            self._say("🗡️🛡️ {} の攻撃+{}・防御+{}".format(self._nm(p.battle), v, e.extra), actor=p.idx)
            self._say("🩸 代償：自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra2), actor=p.idx)
            self._damage_enemy(p, p.battle, e.extra2, source="禁術の代償", by_opponent=False)
        elif t == "heal_self_lock":
            p.battle.hp = min(p.battle.hp_max, p.battle.hp + v)
            p.battle.attack_locked = True
            self._say("💚 {} のHPが{}回復（{}/{}）。代償として次のターン攻撃できない".format(
                self._nm(p.battle), v, p.battle.hp, p.battle.hp_max), actor=p.idx)
        elif t == "weapon_self_defdown":
            p.battle.atk_bonus += v
            p.battle.def_bonus -= e.extra
            p.battle.equipment.append("{}(攻+{})".format(c.name, v))
            p.battle.equipment.append("{}(防-{})".format(c.name, e.extra))
            self._say("🗡️ {} の攻撃+{}・防御-{}".format(self._nm(p.battle), v, e.extra), actor=p.idx)
        elif t == "atk_down_mutual":
            target = o.battle
            if target.atk_debuff_turns <= 0:
                target.atk_bonus -= v
                target.atk_debuff = v
            target.atk_debuff_turns = max(target.atk_debuff_turns, 2)
            self._say("📉 {} の攻撃力が2ターンの間 -{}".format(self._nm(target), v), actor=p.idx)
            p.battle.next_attack_bonus -= e.extra
            self._say("🩸 代償：自分の次の攻撃力-{}".format(e.extra), actor=p.idx)
        elif t == "armor_self_penalty":
            p.battle.def_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🛡️ {} の防御+{}".format(self._nm(p.battle), v), actor=p.idx)
            p.battle.next_attack_bonus -= e.extra
            self._say("🩸 代償：自分の次の攻撃力-{}".format(e.extra), actor=p.idx)
        elif t == "next_move_power_self_cost":
            p.battle.next_attack_bonus += v
            self._say("💪 {} の次の技の威力+{}".format(self._nm(p.battle), v), actor=p.idx)
            self._say("🩸 代償：自分の {} に{}ダメージ".format(self._nm(p.battle), e.extra), actor=p.idx)
            self._damage_enemy(p, p.battle, e.extra, source="禁術の代償", by_opponent=False)
        elif t == "extra_item_use":
            self._say("🩸 代償：自分の {} に{}ダメージ".format(self._nm(p.battle), v), actor=p.idx)
            self._damage_enemy(p, p.battle, v, source="禁術の代償", by_opponent=False)
            p.item_used = False
            self._say("🎒 天罰の裁き符：このターン、もう1回アイテムを使える", actor=p.idx)
        elif t == "weapon_self_lock":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v), actor=p.idx)
            p.stunned = True
            self._say("🩸 代償：{} は次のターン、攻撃も交代もできない".format(p.name), actor=p.idx)
        elif t == "weapon_exclude":
            p.battle.atk_bonus += v
            p.battle.equipment.append("{}(+{})".format(c.name, v))
            self._say("🗡️ {} の攻撃+{}".format(self._nm(p.battle), v), actor=p.idx)
            # apply_action が既にこのカードを item_discard に積んでいるので、
            # そこから取り除いて item_removed へ移す（二度と山札に戻らない）
            if c in self.item_discard:
                self.item_discard.remove(c)
            self.item_removed.append(c)
            self._say("🕳️ {} はゲームから除外された".format(c.name), actor=p.idx)

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
                "enemy_hand": ([] if hide_hand else [c.to_dict() for c in p.enemy_hand]),
                "enemy_hand_count": len(p.enemy_hand),
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
            # 三つ巴：乱入イベントが起きるまでは None。以降は現在の1体と、
            # 山札に残っている数（0＝これが最後の1体）を返す
            "third_force": ({
                "enemy": self.third_force.enemy.to_dict() if self.third_force.enemy else None,
                "deck_count": len(self.third_force.deck),
                "defeated": self.third_force.defeated,
            } if self.third_force.active else None),
            "actions": self.legal_actions(viewer),
            "winner": self.winner,
            "finish_reason": self.finish_reason,
            # 自分に見せてよい行だけ残してから最後の60行を渡す。
            # 相手のベンチ・エネミー手札に触れる行はここで落ちる。
            # actor（誰の行動か。0/1=席番号、None=中立）も一緒に渡し、
            # 画面側で相手の行動だけ色を付けられるようにする。
            "log": [{"text": e.text, "actor": e.actor} for e in self.log
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
