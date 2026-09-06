# -*- coding: utf-8 -*-
"""
Web サーバー。

CPU対戦もLAN対戦も「部屋（room）」として同じ仕組みで扱う。
部屋の中身は server/rooms.py、ゲームのルールは engine/ にある。
ここは HTTP の入り口だけを担当する。

  席0 … 部屋を作った人
  席1 … CPU（CPU対戦） or あとから入ってきた人（LAN対戦）

盤面は必ず `room.view(seat)` を通して返すので、
相手の手札はサーバー側で落とされる。通信を覗いてもカンニングできない。
"""
from __future__ import annotations

import json
import os

from flask import Flask, jsonify, request, send_from_directory

from engine import cards
from engine.ai import CPU_LEVEL_LABELS, CPU_LEVELS, DEFAULT_CPU_LEVEL
from engine.game import DEFAULT_OPTIONS
from engine.reference import build_reference
from engine import skins as skin_store
from server.rooms import REGISTRY, RoomError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="/static")

# Flask は既定で静的ファイルを12時間キャッシュさせる。
# 開発中はこれが致命的で、HTML/CSS/JS を直してもブラウザが古い版を出し続ける。
# （実際にこれで「実装したのに画面に出ない」と1回ハマった）
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def _no_cache(resp):
    """ブラウザにキャッシュさせない。開発用サーバーなので常にこれでよい。"""
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ------------------------------------------------------------ オプション保存
OPTIONS_PATH = os.path.join(ROOT, "user_options.json")


def _load_options() -> dict:
    o = dict(DEFAULT_OPTIONS)
    o["cpu_level"] = DEFAULT_CPU_LEVEL
    try:
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k in DEFAULT_OPTIONS:
            if k in data:
                o[k] = bool(data[k])
        if data.get("cpu_level") in CPU_LEVELS:
            o["cpu_level"] = data["cpu_level"]
    except Exception:
        pass  # 無ければ／壊れていれば既定値でよい
    return o


def _save_options(o: dict):
    try:
        with open(OPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 保存に失敗してもゲームは続行できる


LAST_OPTIONS = {"value": _load_options()}

# カード図鑑は内容が変わらないので、一度作ったら使い回す
REFERENCE = None


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _fail(e: RoomError, code: int = 400):
    return jsonify({"error": str(e)}), code


# ==================================================================== ページ
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


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


@app.route("/api/options")
def api_options():
    """前回選んだオプション。部屋を作る画面の初期値に使う。"""
    return jsonify({
        "options": LAST_OPTIONS["value"],
        "cpu_levels": CPU_LEVEL_LABELS,
        "skins": skin_store.available_skins(),
        "current_skin": skin_store.current_skin_id(),
    })


@app.route("/api/skin", methods=["POST"])
def api_skin():
    """スキン（カード名の見た目セット）を切り替える。

    skin_config.json に保存（次回サーバー起動時の既定値用）した上で、
    cards.apply_skin() を呼んでその場で反映する。サーバー再起動は不要
    （「新しい設定でゲームを始める」＝rematch すれば次の対戦から新しい名前になる）。
    """
    global REFERENCE
    b = _body()
    skin_id = b.get("skin")
    valid_ids = {s["id"] for s in skin_store.available_skins()}
    if skin_id not in valid_ids:
        return jsonify({"error": "そのスキンは存在しません。"}), 400
    skin_store.set_current_skin(skin_id)
    cards.apply_skin(skin_id)
    REFERENCE = None  # カード図鑑のキャッシュも作り直す
    return jsonify({
        "ok": True,
        "skin": skin_id,
        "message": "スキンを「{}」に切り替えました。次に始める対戦から反映されます。".format(skin_id),
    })


# ====================================================================== 部屋
@app.route("/api/room/create", methods=["POST"])
def api_room_create():
    b = _body()
    mode = b.get("mode")
    if mode not in ("cpu", "lan"):
        return jsonify({"error": "モードの指定が不正です。"}), 400
    options = b.get("options")
    cpu_level = b.get("cpu_level")
    if cpu_level not in CPU_LEVELS:
        cpu_level = LAST_OPTIONS["value"].get("cpu_level", DEFAULT_CPU_LEVEL)
    try:
        room = REGISTRY.create(mode, options, b.get("name") or "", cpu_level)
    except RoomError as e:
        return _fail(e)
    if options is not None:
        for k in DEFAULT_OPTIONS:
            LAST_OPTIONS["value"][k] = room.options[k]
    if mode == "cpu":
        LAST_OPTIONS["value"]["cpu_level"] = room.cpu_level
    _save_options(LAST_OPTIONS["value"])
    return jsonify({
        "code": room.code,
        "token": room.tokens[0],
        "seat": 0,
        "state": room.view(0),
    })


@app.route("/api/room/join", methods=["POST"])
def api_room_join():
    b = _body()
    try:
        room, token = REGISTRY.join(b.get("code") or "", b.get("name") or "")
    except RoomError as e:
        return _fail(e)
    return jsonify({
        "code": room.code,
        "token": token,
        "seat": 1,
        "state": room.view(1),
    })


@app.route("/api/room/list")
def api_room_list():
    """まだ相手を待っているLAN部屋の一覧。合言葉を打たずに入れるようにするため。"""
    return jsonify({"rooms": REGISTRY.open_rooms()})


@app.route("/api/room/state")
def api_room_state():
    try:
        room, seat = REGISTRY.authed(request.args.get("code"), request.args.get("token"))
    except RoomError as e:
        return _fail(e, 404)
    return jsonify(room.view(seat))


@app.route("/api/room/action", methods=["POST"])
def api_room_action():
    b = _body()
    try:
        room, seat = REGISTRY.authed(b.get("code"), b.get("token"))
    except RoomError as e:
        return _fail(e, 404)
    ok = room.apply(seat, b.get("action") or {})
    view = room.view(seat)
    view["accepted"] = ok
    return jsonify(view)


@app.route("/api/room/leave", methods=["POST"])
def api_room_leave():
    """相手待ちの部屋をやめる。放置された部屋が一覧に残らないようにするため。"""
    b = _body()
    try:
        REGISTRY.close(b.get("code") or "", b.get("token") or "")
    except RoomError as e:
        return _fail(e)
    return jsonify({"ok": True})


@app.route("/api/room/rename", methods=["POST"])
def api_room_rename():
    """対戦中でも名前を変えられる。相手の画面にもすぐ反映される。"""
    b = _body()
    # 参加者かどうかの確認は 404、入力の不備は 400。他のAPIと同じ扱いに揃える
    try:
        room, seat = REGISTRY.authed(b.get("code"), b.get("token"))
    except RoomError as e:
        return _fail(e, 404)
    try:
        room.rename(seat, b.get("name") or "")
    except RoomError as e:
        return _fail(e)
    return jsonify(room.view(seat))


@app.route("/api/room/rematch", methods=["POST"])
def api_room_rematch():
    """決着後にもう1試合。相手の画面にも自動で反映される。"""
    b = _body()
    try:
        room, seat = REGISTRY.authed(b.get("code"), b.get("token"))
    except RoomError as e:
        return _fail(e, 404)
    if room.mode == "lan" and not room.is_full:
        return jsonify({"error": "相手がまだいません。"}), 400
    options = b.get("options")
    changed = False
    if options is not None:
        for k in DEFAULT_OPTIONS:
            if k in options:
                room.options[k] = bool(options[k])
                LAST_OPTIONS["value"][k] = room.options[k]
        changed = True
    if room.mode == "cpu":
        cpu_level = b.get("cpu_level")
        if cpu_level in CPU_LEVELS:
            room.cpu_level = cpu_level
            LAST_OPTIONS["value"]["cpu_level"] = cpu_level
            changed = True
    if changed:
        _save_options(LAST_OPTIONS["value"])
    room.start_game()
    return jsonify(room.view(seat))


# ==================================================================== 起動
def _local_ips():
    """このPCがLAN内で持っているIPv4アドレスを集める。"""
    import socket
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.add(ip)
    except Exception:
        pass
    try:
        # 外に出るときに使うIPを調べる（実際には通信しない）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips)


def _url(hostpart: str, port: int) -> str:
    """ポート80のときは :80 を省ける。"""
    return "http://{}/".format(hostpart) if port == 80 \
        else "http://{}:{}/".format(hostpart, port)


def print_banner(host: str, port: int):
    import socket
    name = socket.gethostname().lower()
    line = "=" * 62
    print(line)
    print("  🎴 アルカナエクスプロージョン  サーバー起動")
    print(line)
    if host == "0.0.0.0":
        print("  📱 スマホ・ほかのPCから、このどれかを開いてね")
        print("")
        print("      {}        ← いちばん短い（同じLANのWindows PC）".format(_url(name, port)))
        print("      {}  ← スマホ・Mac はこっち".format(_url(name + ".local", port)))
        for ip in _local_ips():
            print("      {}".format(_url(ip, port)))
        print("")
        print("  ⚠️ スマホは「モバイル通信」ではなく Wi-Fi に繋いでね")
        print("  ⚠️ 初回は Windows の確認が出たら「アクセスを許可する」を選んでね")
    else:
        print("  ブラウザで開いてね →  {}".format(_url("localhost", port)))
        print("  （スマホやほかのPCからも繋ぐときは「みんなで遊ぶ」のほうを使ってね）")
    print("")
    print("  止めるときは Ctrl+C")
    print(line)


def main(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    print_banner(host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
