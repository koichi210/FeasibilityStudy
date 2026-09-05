// 攻城戦専用: 城壁・城門・矢櫓（構造物）まわりの処理。
// 構造物はユニットと違って移動しない。矢櫓だけ攻撃してくる（AIが動かす）。

(function () {
  window.KG = window.KG || {};
  const { uid, manhattan } = window.KG.util;

  const STRUCTURE_KIND_INFO = {
    wall: { name: "城壁", icon: "🧱" },
    gate: { name: "城門", icon: "🚪" },
    tower: { name: "矢櫓", icon: "🏯" },
  };

  /** ステージ定義の structures 配列から、戦闘用の構造物インスタンスを作る */
  function createStructures(stageStructures) {
    return stageStructures.map((s) => ({
      id: uid("struct"),
      kind: s.kind, // 'wall' | 'gate' | 'tower'
      r: s.r,
      c: s.c,
      hp: s.hp,
      maxHp: s.hp,
      atk: s.atk || 0,
      range: s.range || 0,
    }));
  }

  function getStructureAt(structures, r, c) {
    return structures.find((s) => s.r === r && s.c === c) || null;
  }

  /** 城壁・城門への攻撃力。攻城兵器は siegeAtk、それ以外のユニットは atk の4割で計算する */
  function siegeDamageOf(unit) {
    if (unit.siegeAtk) return unit.siegeAtk;
    return Math.max(1, Math.ceil(unit.atk * 0.4));
  }

  /** 矢櫓の攻撃対象を選ぶ（射程内の敵ユニットのうち、最もHPが低い相手を狙う） */
  function pickTowerTarget(tower, playerUnits) {
    const inRange = playerUnits.filter(
      (u) => manhattan(tower.r, tower.c, u.r, u.c) <= tower.range
    );
    if (inRange.length === 0) return null;
    inRange.sort((a, b) => a.hp - b.hp);
    return inRange[0];
  }

  window.KG.siege = { STRUCTURE_KIND_INFO, createStructures, getStructureAt, siegeDamageOf, pickTowerTarget };
})();
