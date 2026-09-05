// 編成画面で選んだ「持ち込み武将・城」を localStorage に保存する。
// クリア状況（save.js）とは別のキーで管理する。

(function () {
  window.KG = window.KG || {};

  const KEY = "kingdom-game-roster-v1";

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { equipped: [] };
      const data = JSON.parse(raw);
      if (!Array.isArray(data.equipped)) return { equipped: [] };
      return data;
    } catch (e) {
      return { equipped: [] };
    }
  }

  function save(data) {
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
    } catch (e) {
      // localStorageが使えない環境では無視する（プレイ自体は継続できる）
    }
  }

  /** 編成画面で選べる全ユニット（武将＋城・砦）を一覧で返す */
  function getAllPremiumUnits() {
    const { PREMIUM_HERO_TYPES } = window.KG.characters;
    const { CASTLE_TYPES } = window.KG.castles;
    const heroes = Object.values(PREMIUM_HERO_TYPES).map((t) => ({ ...t, kind: "hero" }));
    const castles = Object.values(CASTLE_TYPES).map((t) => ({ ...t, kind: "castle" }));
    return [...heroes, ...castles];
  }

  function getEquippedIds() {
    return load().equipped;
  }

  function isEquipped(id) {
    return load().equipped.includes(id);
  }

  /** 編成のオン/オフを切り替える。切り替え後の状態(true=編成済み)を返す */
  function toggleEquipped(id) {
    const data = load();
    const idx = data.equipped.indexOf(id);
    let nowEquipped;
    if (idx === -1) {
      data.equipped.push(id);
      nowEquipped = true;
    } else {
      data.equipped.splice(idx, 1);
      nowEquipped = false;
    }
    save(data);
    return nowEquipped;
  }

  window.KG.roster = { getAllPremiumUnits, getEquippedIds, isEquipped, toggleEquipped };
})();
