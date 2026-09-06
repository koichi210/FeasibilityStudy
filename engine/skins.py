# -*- coding: utf-8 -*-
"""
スキン（見た目の差し替えセット）の読み込み。

「アルカナのカード名たち」をデフォルトのスキンとして、`skins/*.json` に
スキンごとのカード名・技名・アイテム名・口上・数値の上書きをまとめて置く。
ルール本体（技のid・ダメージ計算式など）はスキンに関係なく共通で、
cards.py 側の共通コードが担当する。スキンが持つのは「見た目の名前」と、
ごく一部の数値の上書き（balance_overrides）だけ。

スキンの切り替えは `skin_config.json` に選択中のスキンidを保存して行う。
⚙️オプション画面からの切り替えは `cards.apply_skin()`（engine/cards.py）が
モジュール内の辞書をその場で書き換えるので、**サーバー再起動なしで次の対戦から反映される**。
`skin_config.json` への保存は「次回サーバー起動時にもそのスキンで立ち上がるように」
するためのもの（balance.json を手で直接編集したときは、今まで通り再起動が必要）。
"""
from __future__ import annotations

import copy
import json
import os
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKINS_DIR = os.path.join(ROOT, "skins")
SKIN_CONFIG_PATH = os.path.join(ROOT, "skin_config.json")

DEFAULT_SKIN_ID = "arcana"


def available_skins() -> List[Dict[str, str]]:
    """選べるスキンの一覧を [{"id":..., "label":...}] で返す。"""
    result = []
    if not os.path.isdir(SKINS_DIR):
        return [{"id": DEFAULT_SKIN_ID, "label": "アルカナ（デフォルト）"}]
    for fname in sorted(os.listdir(SKINS_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(SKINS_DIR, fname), encoding="utf-8") as f:
            data = json.load(f)
        result.append({"id": data.get("id", fname[:-5]), "label": data.get("label", fname[:-5])})
    return result


def load_skin(skin_id: str) -> dict:
    """指定idのスキンデータを読み込む。無ければデフォルト（arcana）にフォールバック。"""
    path = os.path.join(SKINS_DIR, "{}.json".format(skin_id))
    if not os.path.isfile(path):
        path = os.path.join(SKINS_DIR, "{}.json".format(DEFAULT_SKIN_ID))
    # utf-8-sig … メモ帳などでBOM付きで保存されても読めるように（.ps1と同じハマりどころ）
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def current_skin_id() -> str:
    """現在選択中のスキンidを skin_config.json から読む（無ければデフォルト）。"""
    if not os.path.isfile(SKIN_CONFIG_PATH):
        return DEFAULT_SKIN_ID
    try:
        with open(SKIN_CONFIG_PATH, encoding="utf-8-sig") as f:
            return json.load(f).get("skin", DEFAULT_SKIN_ID)
    except (ValueError, OSError):
        return DEFAULT_SKIN_ID


def set_current_skin(skin_id: str):
    """選択中のスキンidを保存する（次回サーバー起動時の既定値として使う）。

    実際にゲーム内の表示へ反映するには、これとは別に cards.apply_skin() を呼ぶ必要がある
    （呼び出しは server/app.py の /api/skin がまとめて行う）。
    """
    with open(SKIN_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"skin": skin_id}, f, ensure_ascii=False, indent=2)


def merge_balance(base_balance: dict, skin: dict) -> dict:
    """base_balance に skin["balance_overrides"] を深くマージした新しい辞書を返す。"""
    merged = copy.deepcopy(base_balance)
    deep_update_inplace(merged, skin.get("balance_overrides", {}))
    return merged


def deep_update_inplace(dst: dict, src: dict):
    """dst の中身を src の値で「その場で」書き換える（dst自体は新しい辞書に差し替えない）。

    cards.py がスキンをホットリロードするときに使う。BALANCE のようにあちこちの
    モジュールが `from .cards import BALANCE` で辞書オブジェクトそのものを掴んでいる
    場合、辞書を新しいオブジェクトで置き換えても掴んでいる側には反映されない。
    ネストした辞書ごと in-place で書き換えることで、参照を持っている側にも自動で
    伝わるようにしている。
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_update_inplace(dst[k], v)
        else:
            dst[k] = v
