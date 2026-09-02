# -*- coding: utf-8 -*-
"""
バランス検証用のシミュレーター。CPU 同士を大量に対戦させて統計を取る。

    py -3 simulate.py                 … 500戦
    py -3 simulate.py --games 5000
    py -3 simulate.py --games 1 -v    … 1戦だけログを全部出す

balance.json をいじったあとに走らせて、
「試合が何ターンで終わるか」「先攻が有利すぎないか」を数字で確かめる用。
"""
from __future__ import annotations

import argparse
import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from engine.ai import run_cpu_turn  # noqa: E402
from engine.game import Game  # noqa: E402


def play_one(seed: int, verbose: bool = False) -> dict:
    g = Game(seed=seed, names=("先攻", "後攻"), cpu=(True, True))
    g.start()
    guard = 0
    while g.winner is None and guard < 400:
        run_cpu_turn(g)
        guard += 1
    if verbose:
        for line in g.log:
            print(line)
    return {
        "winner": g.winner,
        "turns": g.turn,
        "hp": [p.trainer_hp for p in g.players],
        "reason": g.finish_reason,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    results = [play_one(args.seed + i, args.verbose and args.games == 1)
               for i in range(args.games)]

    wins = collections.Counter(r["winner"] for r in results)
    turns = [r["turns"] for r in results]
    n = len(results)

    print()
    print("=" * 46)
    print(" {} 戦の結果".format(n))
    print("=" * 46)
    print("  先攻の勝率     {:>6.1f}%".format(100 * wins[0] / n))
    print("  後攻の勝率     {:>6.1f}%".format(100 * wins[1] / n))
    print("  引き分け       {:>6.1f}%".format(100 * wins[-1] / n))
    print("-" * 46)
    print("  平均ターン数   {:>6.1f}".format(statistics.mean(turns)))
    print("  最短 / 最長    {:>6} / {}".format(min(turns), max(turns)))
    if n > 1:
        print("  中央値         {:>6.1f}".format(statistics.median(turns)))
    print("-" * 46)
    reasons = collections.Counter(r["reason"] for r in results if r["reason"])
    for r, c in reasons.most_common():
        print("  {} … {}件".format(r, c))
    print("=" * 46)
    print()
    print("💡 ターン数は「手番」の数（両者の合計）。1人あたりの手番はこの半分。")
    print("   目安：合計30〜40手番（1人15〜20手番）、先攻勝率45〜55%くらいだと健全。")
    print("   ズレていたら balance.json の trainer_hp / monster_hp /")
    print("   kill_trainer_damage あたりを調整してね。")


if __name__ == "__main__":
    main()
