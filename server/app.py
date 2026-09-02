# -*- coding: utf-8 -*-
"""
ローカル Web サーバー（PoC 版）。

いまは「1つのゲームを、ブラウザ1人 vs CPU で遊ぶ」だけ。
将来 LAN 対戦にするときは
  * ゲームを部屋(room)単位で複数持つ
  * viewer をプレイヤーごとに切り替える（view() が既に対応済み）
だけで拡張できるようにしてある。
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, request, send_from_directory

from engine.ai import run_cpu_turn
from engine.game import Game

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")

# PoC なのでゲームはプロセス内に1つだけ持つ
STATE = {"game": None}
HUMAN = 0  # ブラウザで操作する側


def _new_game() -> Game:
    g = Game(names=("あなた", "CPU"), cpu=(False, True))
    g.start()
    STATE["game"] = g
    return g


def _game() -> Game:
    if STATE["game"] is None:
        _new_game()
    return STATE["game"]


def _advance_cpu(g: Game):
    """人間の番になるまで CPU を進める。"""
    guard = 0
    while g.winner is None and g.players[g.current].is_cpu and guard < 50:
        run_cpu_turn(g)
        guard += 1


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/api/state")
def api_state():
    return jsonify(_game().view(HUMAN))


@app.route("/api/new", methods=["POST"])
def api_new():
    g = _new_game()
    _advance_cpu(g)
    return jsonify(g.view(HUMAN))


@app.route("/api/action", methods=["POST"])
def api_action():
    g = _game()
    action = (request.get_json(silent=True) or {}).get("action") or {}
    ok = False
    if g.winner is None and g.current == HUMAN:
        ok = g.apply_action(action)
        _advance_cpu(g)
    view = g.view(HUMAN)
    view["accepted"] = ok
    return jsonify(view)


def main(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    _new_game()
    url = "http://{}:{}/".format("localhost" if host == "127.0.0.1" else host, port)
    print("=" * 56)
    print("  🎴 おぐそーのカードゲーム PoC サーバー起動")
    print("  ブラウザで開いてね →  {}".format(url))
    print("  止めるときは Ctrl+C")
    print("=" * 56)
    app.run(host=host, port=port, debug=debug, use_reloader=False)
