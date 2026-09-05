// 盤面（グリッド）・地形まわりの処理。
// 「そのマスに何がいるか」は battle.js 側の状態(state)が持つ。ここは座標計算だけを担当する。

(function () {
  window.KG = window.KG || {};
  const { manhattan } = window.KG.util;

  const TERRAIN_INFO = {
    plain: { name: "平地", moveCost: 1, defenseBonus: 0, rangeBonus: 0, icon: "" },
    hill: { name: "丘", moveCost: 1, defenseBonus: 3, rangeBonus: 0, icon: "⛰️" },
    forest: { name: "森", moveCost: 1, defenseBonus: 1, rangeBonus: 1, icon: "🌲" },
    river: { name: "河川", moveCost: 2, defenseBonus: -1, rangeBonus: 0, icon: "🌊" },
  };

  function createBoard(stage) {
    return {
      cols: stage.cols,
      rows: stage.rows,
      terrain: stage.terrain,
    };
  }

  function inBounds(board, r, c) {
    return r >= 0 && r < board.rows && c >= 0 && c < board.cols;
  }

  function terrainAt(board, r, c) {
    return (board.terrain[r] && board.terrain[r][c]) || "plain";
  }

  function terrainInfoAt(board, r, c) {
    return TERRAIN_INFO[terrainAt(board, r, c)];
  }

  const DIRECTIONS = [
    [-1, 0],
    [1, 0],
    [0, -1],
    [0, 1],
  ];

  /**
   * 移動力 moveBudget の範囲で到達できるマスを求める（ダイクストラ法）。
   * isBlocked(r, c) が true のマスには進入できない（開始マス自身は対象外）。
   * 戻り値: Map<"r,c", 累計移動コスト>（開始マスは含まない）
   */
  function computeReachable(board, startR, startC, moveBudget, isBlocked) {
    const dist = new Map();
    const key = (r, c) => `${r},${c}`;
    dist.set(key(startR, startC), 0);

    const visited = new Set();
    for (;;) {
      // 未確定の中で最小コストのマスを選ぶ（盤面が小さいので線形探索で十分）
      let currentKey = null;
      let currentCost = Infinity;
      for (const [k, cost] of dist) {
        if (!visited.has(k) && cost < currentCost) {
          currentKey = k;
          currentCost = cost;
        }
      }
      if (currentKey === null) break;
      visited.add(currentKey);
      const [r, c] = currentKey.split(",").map(Number);

      for (const [dr, dc] of DIRECTIONS) {
        const nr = r + dr;
        const nc = c + dc;
        if (!inBounds(board, nr, nc)) continue;
        if (isBlocked(nr, nc)) continue;
        const stepCost = TERRAIN_INFO[terrainAt(board, nr, nc)].moveCost;
        const newCost = currentCost + stepCost;
        if (newCost > moveBudget) continue;
        const nk = key(nr, nc);
        if (!dist.has(nk) || newCost < dist.get(nk)) {
          dist.set(nk, newCost);
        }
      }
    }

    dist.delete(key(startR, startC));
    return dist;
  }

  window.KG.board = {
    TERRAIN_INFO,
    createBoard,
    inBounds,
    terrainAt,
    terrainInfoAt,
    computeReachable,
    manhattan,
  };
})();
