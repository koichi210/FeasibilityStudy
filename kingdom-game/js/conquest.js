// 国盗り編の状態管理。地図上の国データ・交渉・ターン進行・統一判定を扱う。
// 実際の合戦（制圧）は provinces.js の generateProvinceBattleStage() で作ったステージを
// 既存の battle.js / mountBattleUI に渡して戦う。決着は resolveConquerResult() で反映する。

(function () {
  window.KG = window.KG || {};
  const { clamp } = window.KG.util;
  const { createProvinceInstances } = window.KG.provinces;

  function pushLog(state, message) {
    state.log.push(message);
    if (state.log.length > 40) state.log.shift();
  }

  function createConquestState() {
    return {
      provinces: createProvinceInstances(),
      hyourou: 20,
      turn: 1,
      unified: false,
      log: ["国盗り編、開幕。まずは隣国から手を伸ばそう。"],
    };
  }

  function getProvinceById(state, id) {
    return state.provinces.find((p) => p.id === id) || null;
  }

  /** 自国に隣接している、まだ自国でない国の一覧 */
  function getActionableTargets(state) {
    const playerIds = new Set(
      state.provinces.filter((p) => p.owner === "player").map((p) => p.id)
    );
    return state.provinces.filter(
      (p) => p.owner !== "player" && p.neighbors.some((n) => playerIds.has(n))
    );
  }

  function negotiateCost(province) {
    return 10 + province.strength * 8;
  }

  function negotiateSuccessChance(province) {
    return clamp(0.85 - province.strength * 0.15, 0.15, 0.85);
  }

  function negotiate(state, provinceId) {
    const province = getProvinceById(state, provinceId);
    if (!province || province.owner === "player") {
      return { ok: false, error: "対象が不正です" };
    }
    if (!getActionableTargets(state).some((p) => p.id === provinceId)) {
      return { ok: false, error: "自国に隣接していません" };
    }
    const cost = negotiateCost(province);
    if (state.hyourou < cost) {
      return { ok: false, error: "兵糧が足りません" };
    }
    state.hyourou -= cost;
    const success = Math.random() < negotiateSuccessChance(province);
    if (success) {
      province.owner = "player";
      pushLog(state, `${province.name}との交渉が成立した！`);
    } else {
      province.strength = Math.min(6, province.strength + 1);
      pushLog(state, `${province.name}との交渉は決裂した…（警戒が強まった）`);
    }
    checkUnification(state);
    return { ok: true, success };
  }

  /** 合戦（制圧）の決着を地図側に反映する */
  function resolveConquerResult(state, provinceId, outcome) {
    const province = getProvinceById(state, provinceId);
    if (!province) return;
    if (outcome === "win") {
      province.owner = "player";
      pushLog(state, `${province.name}を制圧した！`);
    } else {
      pushLog(state, `${province.name}攻めは失敗に終わった…`);
    }
    checkUnification(state);
  }

  function endConquestTurn(state) {
    const ownedCount = state.provinces.filter((p) => p.owner === "player").length;
    const income = 5 + 3 * ownedCount;
    state.hyourou += income;
    state.turn += 1;
    for (const p of state.provinces) {
      if (p.owner !== "player" && Math.random() < 0.25) {
        p.strength = Math.min(6, p.strength + 1);
      }
    }
    pushLog(state, `--- ターン${state.turn}（兵糧+${income}） ---`);
  }

  function checkUnification(state) {
    if (!state.unified && state.provinces.every((p) => p.owner === "player")) {
      state.unified = true;
      pushLog(state, "天下統一！");
    }
    return state.unified;
  }

  window.KG.conquest = {
    createConquestState,
    getProvinceById,
    getActionableTargets,
    negotiateCost,
    negotiateSuccessChance,
    negotiate,
    resolveConquerResult,
    endConquestTurn,
    checkUnification,
  };
})();
