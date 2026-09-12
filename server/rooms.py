# -*- coding: utf-8 -*-
"""
部屋（room）の管理。

CPU対戦もLAN対戦も「部屋」として同じ形で扱う。
違いは席1（seat 1）に座るのが CPU か人間か、それだけ。

  席0 … 部屋を作った人
  席1 … CPU（CPU対戦） or あとから入ってきた人（LAN対戦）

⚠️ 大事なところ
  盤面は必ず `game.view(seat)` を通して返す。
  この関数が相手の手札を落としてくれるので、
  通信を覗かれてもカンニングできない。
"""
from __future__ import annotations

import random
import secrets
import threading
import time
from typing import Dict, List, Optional

from engine.ai import CPU_LEVEL_LABELS, CPU_LEVELS, DEFAULT_CPU_LEVEL, choose_action
from engine.game import DEFAULT_OPTIONS, Game

# 紛らわしい文字（0/O、1/I/L）を除いた合言葉用の文字
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 4

# 部屋を掃除する条件。「席を外している人の部屋を消さない」ことを最優先にしている。
#   ⚠️ 経過時間ではなく「最後に誰かが見に来てからの時間」で判定すること。
#      作成からの経過時間で消すと、長時間の対戦の途中で部屋が消えてしまう。
ROOM_TTL = 3 * 60 * 60        # 誰も見に来なくなって3時間で掃除する
FINISHED_TTL = 30 * 60        # 決着後30分で掃除する
OFFLINE_AFTER = 15            # 何秒アクセスが無ければ「切断中」とみなすか
MAX_ROOMS = 50

# 相手待ちのまま放置された部屋を消すまでの時間。
# 待機画面にいる間はブラウザが1.2秒ごとに見に来るので、
# これを過ぎている＝画面を閉じた／別のことをしている、と判断できる。
# （放っておくと「入る部屋の一覧」がゴミだらけになる）
#
# ⚠️ 短くしすぎないこと。
#    「部屋を作ったけど、相手が繋ぎ方に手間取っている」という場面は普通にある。
#    慣れていない人が家族に聞きながら設定していると数分かかる。
#    ゴミが少し残るほうが、待っている人の部屋が消えるより百倍マシ。
WAITING_TTL = 5 * 60


class RoomError(Exception):
    """部屋の操作に失敗したときのエラー。メッセージはそのまま画面に出す。"""


class Room:
    def __init__(self, code: str, mode: str, options: dict, host_name: str,
                 cpu_level: str = DEFAULT_CPU_LEVEL):
        self.code = code
        self.mode = mode                      # "cpu" | "lan"
        self.options = dict(options)
        self.cpu_level = cpu_level if cpu_level in CPU_LEVELS else DEFAULT_CPU_LEVEL
        self.names: List[Optional[str]] = [host_name, "CPU" if mode == "cpu" else None]
        self.tokens: List[Optional[str]] = [secrets.token_urlsafe(12), None]
        self.last_seen: List[float] = [time.time(), 0.0]
        self.skins: List[Optional[str]] = [None, None]  # プレイヤーごとのスキン（None = デフォルト）
        self.game: Optional[Game] = None
        self.rev = 0                          # 盤面が変わるたびに増える（画面の更新判定用）
        self.created = time.time()
        self.finished_at: Optional[float] = None
        if mode == "cpu":
            self.start_game()

    # ------------------------------------------------------------ 進行
    def start_game(self):
        # CPU対戦の場合は、敵のスキンをランダムに選ぶ（ゲーム開始の前に設定）
        if self.mode == "cpu":
            from engine import skins as skin_store
            available = skin_store.available_skins()
            if available:
                self.skins[1] = random.choice(available)["id"]

        self.game = Game(
            names=(self.names[0] or "プレイヤー1", self.names[1] or "プレイヤー2"),
            cpu=(False, self.mode == "cpu"),
            options=self.options,
        )
        self.game.start()
        self.finished_at = None
        self.rev += 1
        # CPUの手は画面が1つずつ取りに来る（cpu_step）ので、ここでは進めない

    @property
    def cpu_thinking(self) -> bool:
        """CPUがまだ指すべき手を持っているか（画面が続きを取りに来る目印）。"""
        if not self.game or self.game.winner is not None:
            return False
        if self.game.waiting_for_human_choice():
            return False       # 人間が繰り上げを選ぶのが先
        return self.game.players[self.game.current].is_cpu

    def cpu_step(self) -> bool:
        """CPUの手を **1つだけ** 進める。

        まとめて1ターン分進めてしまうと、画面に届くのは全部終わった後の
        盤面だけになり、攻撃モーションを出したくても
        「攻撃したカードはもうベンチに下がっている」といったことが起きる。
        1手ずつ返して、画面がそのつど演出を見せられるようにする。
        """
        if not self.cpu_thinking:
            return False
        act = choose_action(self.game, self.cpu_level)
        if not self.game.apply_action(act):
            self.game.apply_action({"type": "end_turn"})
        self.rev += 1
        if self.game.winner is not None and self.finished_at is None:
            self.finished_at = time.time()
        return True

    @property
    def is_full(self) -> bool:
        return self.tokens[0] is not None and self.tokens[1] is not None

    @property
    def started(self) -> bool:
        return self.game is not None

    def seat_of(self, token: str) -> Optional[int]:
        if not token:
            return None
        # compare_digest は非ASCIIの str を渡すと例外になるので、バイト列で比べる
        try:
            given = str(token).encode("utf-8")
        except Exception:
            return None
        for i, t in enumerate(self.tokens):
            if t and secrets.compare_digest(t.encode("utf-8"), given):
                return i
        return None

    def join(self, name: str) -> str:
        if self.mode != "lan":
            raise RoomError("この部屋はCPU対戦用です。")
        if self.tokens[1]:
            raise RoomError("この部屋はもう満員です。")
        self.tokens[1] = secrets.token_urlsafe(12)
        self.names[1] = name
        self.last_seen[1] = time.time()
        self.start_game()          # 2人そろったので開始
        return self.tokens[1]

    def touch(self, seat: int):
        self.last_seen[seat] = time.time()

    def rename(self, seat: int, name: str) -> str:
        """対戦中でも名前を変えられるようにする。ゲームの進行には影響しない。"""
        name = (name or "").strip()[:12]
        if not name:
            raise RoomError("名前を入れてね。")
        self.names[seat] = name
        if self.game:
            self.game.players[seat].name = name
        self.rev += 1
        return name

    def opponent_online(self, seat: int) -> bool:
        other = 1 - seat
        if self.mode == "cpu":
            return True
        if not self.tokens[other]:
            return False
        return (time.time() - self.last_seen[other]) < OFFLINE_AFTER

    def apply(self, seat: int, action: dict) -> bool:
        if not self.game or self.game.winner is not None:
            return False

        # 画面がCPUの続きを1手ぶん取りに来た合図。
        # 指すのはCPUなので、席の一致は見ない。
        if action.get("type") == "cpu_step":
            return self.cpu_step()

        # バトル場の繰り上げ選択だけは、相手の番の最中でも自分に権利がある
        pend = self.game.pending_seat()
        if pend is not None:
            if seat != pend:
                return False
        elif self.game.current != seat:
            return False           # 自分の番でなければ何もしない
        ok = self.game.apply_action(action)
        if ok:
            self.rev += 1
            # CPUの続きはここで一気に進めない。画面が cpu_step で1手ずつ取りに来る。
        if self.game.winner is not None and self.finished_at is None:
            self.finished_at = time.time()
        return ok

    # ------------------------------------------------------------ 表示
    def view(self, seat: int) -> dict:
        d = {
            "room": {
                "code": self.code,
                "mode": self.mode,
                "seat": seat,
                "names": [self.names[0], self.names[1]],
                "waiting": not self.started,
                "opponent_online": self.opponent_online(seat),
                "cpu_level": self.cpu_level if self.mode == "cpu" else None,
                "cpu_level_label": (CPU_LEVEL_LABELS.get(self.cpu_level)
                                     if self.mode == "cpu" else None),
                # CPUの手がまだ残っている＝画面は演出を見せ終えたら続きを取りに来る
                "cpu_thinking": self.cpu_thinking,
                "my_skin": self.skins[seat],  # 自分のスキン
                # ゲーム進行中（スキン変更を禁止するため）
                "game_active": self.game is not None and self.game.winner is None,
            },
            "rev": self.rev,
        }
        if self.game:
            d.update(self.game.view(seat))
            # スキンに基づいてカード名を置き換え
            from engine import skins as skin_store

            # 自分のスキンを適用
            if self.skins[seat]:
                skin_data = skin_store.load_skin(self.skins[seat])
                self._replace_card_names_for_player(d, seat, skin_data, is_self=True)

            # 相手のスキンも適用（opponent の敵名を相手のスキンで表示）
            opponent_seat = 1 - seat  # 0 <-> 1
            if self.skins[opponent_seat]:
                skin_data = skin_store.load_skin(self.skins[opponent_seat])
                self._replace_opponent_card_names(d, skin_data)
        else:
            # まだ相手が来ていない
            d.update({
                "turn": 0, "current": 0, "is_my_turn": False, "viewer": seat,
                "options": dict(self.options), "actions": [], "log": [],
                "winner": None, "finish_reason": "",
            })
        return d

    def _replace_card_names_for_player(self, view_data: dict, seat: int, skin_data: dict,
                                        is_self: bool = True) -> None:
        """特定プレイヤーのカード名をスキンに基づいて置き換える"""
        from engine import cards as cards_module
        import re

        if is_self:
            player_key = "me"
            opponent_key = "opponent"
        else:
            player_key = "opponent"
            opponent_key = "me"

        enemy_names = skin_data.get("enemy_names", {})
        face_enemy_names = skin_data.get("face_enemy_names", {})
        face_ability_names = skin_data.get("face_ability_names", {})
        item_number_names = skin_data.get("item_number_names", {})

        def replace_card_name(card: dict, is_player_card: bool) -> None:
            if not card:
                return
            if card.get("kind") == "item":
                # アイテムの場合
                code = card.get("code", "")
                suit = code[0] if code else ""
                rank_str = code[1:] if len(code) > 1 else ""

                # 絵札（J/Q/K/A）のアイテムの場合
                if rank_str in ["J", "Q", "K", "A"]:
                    item_face_names = skin_data.get("item_face_names", {})
                    if code in item_face_names:
                        card["name"] = item_face_names[code]
                else:
                    # 数字カード（2-10）のアイテムの場合
                    if rank_str.isdigit():
                        rank = int(rank_str)
                    else:
                        rank = None

                    if rank and suit in item_number_names and isinstance(item_number_names[suit], list):
                        idx = rank - 2  # ランク2=インデックス0
                        if 0 <= idx < len(item_number_names[suit]):
                            card["name"] = item_number_names[suit][idx]
            elif card.get("kind") == "enemy":
                # エネミーの場合
                code = card.get("code", "")
                suit = code[0] if code else ""
                rank_str = code[1:] if len(code) > 1 else ""

                # 絵札（J/Q/K/A）の場合
                if rank_str in ["J", "Q", "K", "A"]:
                    if code in face_enemy_names:
                        card["name"] = face_enemy_names[code]
                    # 技名も置き換え
                    if card.get("ability") and code in face_ability_names:
                        card["ability"]["name"] = face_ability_names[code]
                else:
                    # 数字カード（2-10）の場合
                    if rank_str.isdigit():
                        rank = int(rank_str)
                    else:
                        rank = None

                    if rank and suit in enemy_names and isinstance(enemy_names[suit], list):
                        idx = rank - 2  # ランク2=インデックス0
                        if 0 <= idx < len(enemy_names[suit]):
                            card["name"] = enemy_names[suit][idx]
                # 技名も置き換え
                if card.get("ability"):
                    ability_id = card["ability"].get("id", "")
                    if ability_id in face_ability_names:
                        card["ability"]["name"] = face_ability_names[ability_id]

        # プレイヤーのカード置き換え
        if player_key in view_data:
            if view_data[player_key].get("battle"):
                replace_card_name(view_data[player_key]["battle"], is_player_card=True)
            for bench_card in view_data[player_key].get("bench", []):
                replace_card_name(bench_card, is_player_card=True)
            for hand_card in view_data[player_key].get("hand", []):
                replace_card_name(hand_card, is_player_card=True)
            if is_self:  # 自分の場合のみ、相手の敵手札を見せる（隠れる側は不要）
                for enemy_hand_card in view_data[player_key].get("enemy_hand", []):
                    replace_card_name(enemy_hand_card, is_player_card=False)

        # 相手のカード置き換え（opponent の敵だけ）
        if opponent_key in view_data and not is_self:
            print(f"[DEBUG] Replacing opponent cards. opponent_key={opponent_key}, is_self={is_self}")
            if view_data[opponent_key].get("battle"):
                print(f"[DEBUG] Opponent battle card: {view_data[opponent_key]['battle']}")
                replace_card_name(view_data[opponent_key]["battle"], is_player_card=False)
                print(f"[DEBUG] After replacement: {view_data[opponent_key]['battle']}")
            for bench_card in view_data[opponent_key].get("bench", []):
                replace_card_name(bench_card, is_player_card=False)

        # ログ内の敵名を置き換え（自分のスキンでのみ置き換え）
        if is_self and "log" in view_data:
            import re
            # ログ内で敵名を置き換えるための逆引き辞書を作成
            default_to_skin_enemy = {}
            for suit in ["H", "D", "C", "S"]:
                if suit in cards_module.ENEMY_NAMES and suit in enemy_names:
                    default_names = cards_module.ENEMY_NAMES.get(suit, [])
                    skin_names = enemy_names.get(suit, [])
                    for i, (default_name, skin_name) in enumerate(zip(default_names, skin_names)):
                        if default_name != skin_name:
                            default_to_skin_enemy[default_name] = skin_name

            for entry in view_data["log"]:
                if "text" in entry:
                    text = entry["text"]
                    # ログテキスト内でデフォルト敵名をスキン適用後の名前に置き換える
                    for default_name, skin_name in default_to_skin_enemy.items():
                        # 「♠J の こうげき」など、敵名の前後に記号や句読点が来る場合を考慮
                        text = re.sub(r'\b' + re.escape(default_name) + r'\b', skin_name, text)
                    entry["text"] = text

    def _replace_opponent_card_names(self, view_data: dict, skin_data: dict) -> None:
        """敵（opponent）のカード名をスキンに基づいて置き換える（敵視点）"""
        from engine import cards as cards_module
        import re

        enemy_names = skin_data.get("enemy_names", {})
        face_enemy_names = skin_data.get("face_enemy_names", {})
        face_ability_names = skin_data.get("face_ability_names", {})
        item_number_names = skin_data.get("item_number_names", {})

        def replace_card_name(card: dict) -> None:
            if not card:
                return
            if card.get("kind") == "item":
                # アイテムの場合
                code = card.get("code", "")
                suit = code[0] if code else ""
                rank_str = code[1:] if len(code) > 1 else ""

                if rank_str in ["J", "Q", "K", "A"]:
                    item_face_names = skin_data.get("item_face_names", {})
                    if code in item_face_names:
                        card["name"] = item_face_names[code]
                else:
                    if rank_str.isdigit():
                        rank = int(rank_str)
                    else:
                        rank = None
                    if rank and suit in item_number_names and isinstance(item_number_names[suit], list):
                        idx = rank - 2
                        if 0 <= idx < len(item_number_names[suit]):
                            card["name"] = item_number_names[suit][idx]
            elif card.get("kind") == "enemy":
                # エネミーの場合
                code = card.get("code", "")
                suit = code[0] if code else ""
                rank_str = code[1:] if len(code) > 1 else ""

                if rank_str in ["J", "Q", "K", "A"]:
                    if code in face_enemy_names:
                        card["name"] = face_enemy_names[code]
                    if card.get("ability") and code in face_ability_names:
                        card["ability"]["name"] = face_ability_names[code]
                else:
                    if rank_str.isdigit():
                        rank = int(rank_str)
                    else:
                        rank = None
                    if rank and suit in enemy_names and isinstance(enemy_names[suit], list):
                        idx = rank - 2
                        if 0 <= idx < len(enemy_names[suit]):
                            card["name"] = enemy_names[suit][idx]
                if card.get("ability"):
                    ability_id = card["ability"].get("id", "")
                    if ability_id in face_ability_names:
                        card["ability"]["name"] = face_ability_names[ability_id]

        # 敵（opponent）のカード置き換え
        if "opponent" in view_data:
            if view_data["opponent"].get("battle"):
                replace_card_name(view_data["opponent"]["battle"])
            for bench_card in view_data["opponent"].get("bench", []):
                replace_card_name(bench_card)

    def summary(self) -> dict:
        return {
            "code": self.code,
            "host": self.names[0],
            "waiting_seconds": int(time.time() - self.created),
            "options": dict(self.options),
        }


# ==========================================================================
# 部屋の置き場所
# ==========================================================================
class RoomRegistry:
    def __init__(self):
        self._rooms: Dict[str, Room] = {}
        self._lock = threading.Lock()

    def _new_code(self) -> str:
        for _ in range(200):
            code = "".join(random.choice(CODE_CHARS) for _ in range(CODE_LEN))
            if code not in self._rooms:
                return code
        raise RoomError("部屋がいっぱいです。しばらくしてからやり直してください。")

    def _cleanup(self):
        now = time.time()
        for code, r in list(self._rooms.items()):
            # 「最後に誰かが見に来てから」で測る。
            # トイレや食事で1時間離れても、対戦中の部屋は消えない。
            idle = now - max(r.last_seen)
            too_old = idle > ROOM_TTL
            done = (r.finished_at is not None
                    and (now - r.finished_at) > FINISHED_TTL)
            # 相手待ちのまま、作った人も見に来なくなった部屋（＝一覧のゴミ）
            abandoned = (r.mode == "lan" and not r.is_full
                         and (now - r.last_seen[0]) > WAITING_TTL)
            if too_old or done or abandoned:
                del self._rooms[code]

    def close(self, code: str, token: str):
        """作った人が「やめる」を押したときに、その場で部屋を閉じる。"""
        room = self.get(code)
        seat = room.seat_of(token or "")
        if seat is None:
            raise RoomError("この部屋の参加者として確認できませんでした。")
        # 対戦がもう始まっている部屋は消さない（相手が困るため）
        if room.is_full and room.started:
            raise RoomError("対戦中の部屋は閉じられません。")
        with self._lock:
            self._rooms.pop(room.code, None)

    def create(self, mode: str, options: Optional[dict], host_name: str,
               cpu_level: Optional[str] = None) -> Room:
        with self._lock:
            self._cleanup()
            if len(self._rooms) >= MAX_ROOMS:
                raise RoomError("部屋が多すぎます。しばらくしてからやり直してください。")
            opts = dict(DEFAULT_OPTIONS)
            if options:
                for k in DEFAULT_OPTIONS:
                    if k in options:
                        opts[k] = bool(options[k])
            level = cpu_level if cpu_level in CPU_LEVELS else DEFAULT_CPU_LEVEL
            room = Room(self._new_code(), mode, opts, host_name or "プレイヤー1",
                        cpu_level=level)
            self._rooms[room.code] = room
            return room

    def get(self, code: str) -> Room:
        with self._lock:
            r = self._rooms.get((code or "").strip().upper())
        if not r:
            raise RoomError("その合言葉の部屋は見つかりませんでした。")
        return r

    def join(self, code: str, name: str):
        room = self.get(code)
        with self._lock:
            token = room.join(name or "プレイヤー2")
        return room, token

    def open_rooms(self) -> List[dict]:
        """まだ相手を待っているLAN部屋の一覧。合言葉を打たずに入れるようにするため。"""
        with self._lock:
            self._cleanup()
            return [r.summary() for r in self._rooms.values()
                    if r.mode == "lan" and not r.is_full]

    def authed(self, code: str, token: str):
        """合言葉とトークンから、部屋と席を取り出す。"""
        room = self.get(code)
        seat = room.seat_of(token or "")
        if seat is None:
            raise RoomError("この部屋の参加者として確認できませんでした。入り直してください。")
        room.touch(seat)
        return room, seat


REGISTRY = RoomRegistry()
