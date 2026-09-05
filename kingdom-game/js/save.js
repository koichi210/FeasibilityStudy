// クリア状況を localStorage に保存する。別ブラウザ・別PCには引き継がれない。

(function () {
  window.KG = window.KG || {};

  const KEY = "kingdom-game-save-v1";

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { clearedStages: [] };
      const data = JSON.parse(raw);
      if (!Array.isArray(data.clearedStages)) return { clearedStages: [] };
      return data;
    } catch (e) {
      return { clearedStages: [] };
    }
  }

  function getClearedStages() {
    return load().clearedStages;
  }

  function isStageCleared(stageId) {
    return load().clearedStages.includes(stageId);
  }

  function markStageCleared(stageId) {
    const data = load();
    if (!data.clearedStages.includes(stageId)) {
      data.clearedStages.push(stageId);
    }
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
    } catch (e) {
      // localStorageが使えない環境では無視する（プレイ自体は継続できる）
    }
  }

  window.KG.save = { getClearedStages, isStageCleared, markStageCleared };
})();
