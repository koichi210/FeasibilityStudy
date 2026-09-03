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

import json
import os

from flask import Flask, jsonify, request, send_from_directory

from engine.ai import run_cpu_turn
from engine.game import DEFAULT_OPTIONS, Game
from engine.reference import build_reference

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")

# オプションは次に起動したときも覚えていてほしいので、ファイルに残す
OPTIONS_PATH = os.path.join(ROOT, "user_options.json")


def _load_options() -> dict:
    o = dict(DEFAULT_OPTIONS)
    try:
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k in DEFAULT_OPTIONS:
            if k in data:
                o[k] = bool(data[k])
    except Exception:
        pass  # 無ければ／壊れていれば既定値でよい
    return o


def _save_options(o: dict):
    try:
        with open(OPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 保存に失敗してもゲームは続行できる


# PoC なのでゲームはプロセス内に1つだけ持つ
STATE = {"game": None, "options": _load_options()}
HUMAN = 0  # ブラウザで操作する側

# カード図鑑は内容が変わらないので、一度作ったら使い回す
REFERENCE = None


def _new_game(options=None) -> Game:
    g = Game(names=("あなた", "CPU"), cpu=(False, True),
             options=options if options is not None else STATE["options"])
    g.start()
    STATE["game"] = g
    STATE["options"] = dict(g.options)
    if options is not None:
        _save_options(STATE["options"])
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


@app.route("/cards")
def cards_page():
    """カード図鑑の単独ページ。別タブで開いたり、印刷して早見表にしたりする用。"""
    return send_from_directory(WEB_DIR, "cards.html")


@app.route("/api/reference")
def api_reference():
    """カード図鑑のデータ。実際のカード定義から作るので表示がズレない。"""
    global REFERENCE
    if REFERENCE is None:
        REFERENCE = build_reference()
    return jsonify(REFERENCE)


@app.route("/api/new", methods=["POST"])
def api_new():
    body = request.get_json(silent=True) or {}
    g = _new_game(body.get("options"))
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
