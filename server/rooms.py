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

from engine.ai import run_cpu_turn
from engine.game import DEFAULT_OPTIONS, Game

# 紛らわしい文字（0/O、1/I/L）を除いた合言葉用の文字
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 4

ROOM_TTL = 3 * 60 * 60        # 3時間で部屋を掃除する
FINISHED_TTL = 30 * 60        # 決着後30分で掃除する
OFFLINE_AFTER = 15            # 何秒アクセスが無ければ「切断中」とみなすか
MAX_ROOMS = 50


class RoomError(Exception):
    """部屋の操作に失敗したときのエラー。メッセージはそのまま画面に出す。"""


class Room:
    def __init__(self, code: str, mode: str, options: dict, host_name: str):
        self.code = code
        self.mode = mode                      # "cpu" | "lan"
        self.options = dict(options)
        self.names: List[Optional[str]] = [host_name, "CPU" if mode == "cpu" else None]
        self.tokens: List[Optional[str]] = [secrets.token_urlsafe(12), None]
        self.last_seen: List[float] = [time.time(), 0.0]
        self.game: Optional[Game] = None
        self.rev = 0                          # 盤面が変わるたびに増える（画面の更新判定用）
        self.created = time.time()
        self.finished_at: Optional[float] = None
        if mode == "cpu":
            self.start_game()

    # ------------------------------------------------------------ 進行
    def start_game(self):
        self.game = Game(
            names=(self.names[0] or "プレイヤー1", self.names[1] or "プレイヤー2"),
            cpu=(False, self.mode == "cpu"),
            options=self.options,
        )
        self.game.start()
        self.finished_at = None
        self.rev += 1
        if self.mode == "cpu":
            self._advance_cpu()

    def _advance_cpu(self):
        guard = 0
        while (self.game.winner is None
               and self.game.players[self.game.current].is_cpu and guard < 50):
            run_cpu_turn(self.game)
            guard += 1
        self.rev += 1

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
        if self.game.current != seat:
            return False           # 自分の番でなければ何もしない
        ok = self.game.apply_action(action)
        if ok:
            self.rev += 1
            if self.mode == "cpu":
                self._advance_cpu()
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
            },
            "rev": self.rev,
        }
        if self.game:
            d.update(self.game.view(seat))
        else:
            # まだ相手が来ていない
            d.update({
                "turn": 0, "current": 0, "is_my_turn": False, "viewer": seat,
                "options": dict(self.options), "actions": [], "log": [],
                "winner": None, "finish_reason": "",
            })
        return d

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
            too_old = (now - r.created) > ROOM_TTL
            done = (r.finished_at is not None
                    and (now - r.finished_at) > FINISHED_TTL)
            if too_old or done:
                del self._rooms[code]

    def create(self, mode: str, options: Optional[dict], host_name: str) -> Room:
        with self._lock:
            self._cleanup()
            if len(self._rooms) >= MAX_ROOMS:
                raise RoomError("部屋が多すぎます。しばらくしてからやり直してください。")
            opts = dict(DEFAULT_OPTIONS)
            if options:
                for k in DEFAULT_OPTIONS:
                    if k in options:
                        opts[k] = bool(options[k])
            room = Room(self._new_code(), mode, opts, host_name or "プレイヤー1")
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
