// CPU（敵軍）の思考ルーチン。ルールベースの簡易AI。
// 方針: 射程内に自軍がいれば最もHPが低い相手を狙う。いなければ最も近い自軍ユニットへ前進する。

(function () {
  window.KG = window.KG || {};
  const { manhattan } = window.KG.util;
  const {
    getReachableCells,
    getAttackableTargets,
    actionMove,
    actionAttackUnit,
    actionWait,
    computeDamage,
    applyDamageToUnit,
    pushLog,
  } = window.KG.battle;
  const { pickTowerTarget } = window.KG.siege;

  function pickAttackTarget(units) {
    if (units.length === 0) return null;
    return [...units].sort((a, b) => a.hp - b.hp)[0];
  }

  function findBestMoveTowards(reachable, fromR, fromC, targetR, targetC) {
    let best = null;
    let bestDist = manhattan(fromR, fromC, targetR, targetC);
    for (const key of reachable.keys()) {
      const [r, c] = key.split(",").map(Number);
      const d = manhattan(r, c, targetR, targetC);
      if (d < bestDist) {
        bestDist = d;
        best = { r, c };
      }
    }
    return best;
  }

  function runEnemyTurn(state) {
    const enemyUnitIds = state.units
      .filter((u) => u.ownerId === "enemy" && !u.isHQ)
      .map((u) => u.id);

    for (const id of enemyUnitIds) {
      const unit = state.units.find((u) => u.id === id);
      if (!unit || unit.acted) continue;

      let { units: targets } = getAttackableTargets(state, unit);
      if (targets.length === 0) {
        const playerUnits = state.units.filter((u) => u.ownerId === "player");
        if (playerUnits.length > 0) {
          const nearest = [...playerUnits].sort(
            (a, b) =>
              manhattan(unit.r, unit.c, a.r, a.c) - manhattan(unit.r, unit.c, b.r, b.c)
          )[0];
          const reachable = getReachableCells(state, unit);
          const dest = findBestMoveTowards(reachable, unit.r, unit.c, nearest.r, nearest.c);
          if (dest) {
            actionMove(state, unit, dest.r, dest.c);
            targets = getAttackableTargets(state, unit).units;
          }
        }
      }

      if (targets.length > 0 && !unit.acted) {
        const target = pickAttackTarget(targets);
        actionAttackUnit(state, unit, target);
      } else if (!unit.acted) {
        actionWait(state, unit);
      }
    }

    // 矢櫓（攻城戦のみ）: 射程内の自軍ユニットのうちHPが低い相手を狙う
    const towers = state.structures.filter((s) => s.kind === "tower" && s.hp > 0);
    for (const tower of towers) {
      const playerUnits = state.units.filter((u) => u.ownerId === "player");
      const target = pickTowerTarget(tower, playerUnits);
      if (!target) continue;
      const dmg = computeDamage({ atk: tower.atk, beatsCategory: null }, target, state.board);
      applyDamageToUnit(state, target, dmg, "矢櫓");
    }

    pushLog(state, "敵の行動が終了した。");
  }

  window.KG.ai = { runEnemyTurn };
})();
