// 国盗り編: 国データと、国の強さから即席の合戦ステージを作る関数。
// 令制国名は史実の地名（著作権上の配慮は不要）。隣接関係は実際の地理を大まかに踏襲。

(function () {
  window.KG = window.KG || {};

  const P = "plain";
  const H = "hill";
  const F = "forest";
  const R = "river";

  // 合戦ステージ用の共通地形（field1と同じレイアウトを流用し、雰囲気の一貫性を優先）
  const STANDARD_TERRAIN = [
    [P, P, H, P, H, P, P],
    [P, F, P, P, P, F, P],
    [P, P, R, R, R, P, P],
    [P, H, P, P, P, H, P],
    [P, P, P, P, P, P, P],
    [P, P, P, P, P, P, P],
  ];

  // 敵ユニットの配置スロット（強さに応じて先頭から使う）
  const ENEMY_SLOTS = [
    { r: 2, c: 1 },
    { r: 2, c: 5 },
    { r: 1, c: 3 },
    { r: 2, c: 3 },
    { r: 1, c: 1 },
  ];

  // 20カ国、全国をカバー（尾張=本拠地から、東北・関東・北陸・近畿・中国・四国・九州へ広がる）
  const PROVINCES = [
    { id: "owari", name: "尾張", neighbors: ["mikawa", "mino", "ise"], x: 40, y: 55, strength: 0, isHome: true },
    { id: "mikawa", name: "三河", neighbors: ["owari", "ise", "totomi"], x: 55, y: 62, strength: 2 },
    { id: "mino", name: "美濃", neighbors: ["owari", "omi", "shinano"], x: 38, y: 33, strength: 1 },
    { id: "ise", name: "伊勢", neighbors: ["owari", "mikawa", "yamato"], x: 33, y: 78, strength: 1 },
    { id: "omi", name: "近江", neighbors: ["mino", "echizen", "yamashiro"], x: 18, y: 35, strength: 2 },
    { id: "suruga", name: "駿河", neighbors: ["totomi", "kai", "musashi"], x: 70, y: 55, strength: 2 },
    { id: "kai", name: "甲斐", neighbors: ["suruga", "shinano", "kouzuke"], x: 76, y: 33, strength: 3 },
    { id: "echizen", name: "越前", neighbors: ["omi", "kaga"], x: 10, y: 14, strength: 3 },
    // 東海・中部
    { id: "totomi", name: "遠江", neighbors: ["mikawa", "suruga"], x: 62, y: 60, strength: 2 },
    { id: "shinano", name: "信濃", neighbors: ["mino", "kai"], x: 55, y: 40, strength: 2 },
    // 北陸
    { id: "kaga", name: "加賀", neighbors: ["echizen"], x: 14, y: 22, strength: 4 },
    // 関東
    { id: "musashi", name: "武蔵", neighbors: ["suruga", "kouzuke"], x: 68, y: 44, strength: 3 },
    { id: "kouzuke", name: "上野", neighbors: ["kai", "musashi", "mutsu"], x: 66, y: 26, strength: 4 },
    // 東北
    { id: "mutsu", name: "陸奥", neighbors: ["kouzuke"], x: 75, y: 8, strength: 5 },
    // 近畿
    { id: "yamashiro", name: "山城", neighbors: ["omi", "yamato", "harima"], x: 10, y: 46, strength: 3 },
    { id: "yamato", name: "大和", neighbors: ["ise", "yamashiro"], x: 18, y: 64, strength: 2 },
    // 中国
    { id: "harima", name: "播磨", neighbors: ["yamashiro", "aki"], x: 2, y: 50, strength: 4 },
    { id: "aki", name: "安芸", neighbors: ["harima", "iyo"], x: 2, y: 74, strength: 5 },
    // 四国
    { id: "iyo", name: "伊予", neighbors: ["aki", "chikuzen"], x: 10, y: 90, strength: 5 },
    // 九州
    { id: "chikuzen", name: "筑前", neighbors: ["iyo"], x: 2, y: 95, strength: 6 },
  ];

  function createProvinceInstances() {
    return PROVINCES.map((p) => ({ ...p, owner: p.isHome ? "player" : "rival" }));
  }

  /** 強さに応じた敵部隊構成を組み立てる（既存の兵種のみ使用、新規ユニットは作らない） */
  function buildEnemyComposition(strength) {
    const comp = ["infantry", "infantry"];
    if (strength >= 2) comp.push("archer");
    if (strength >= 3) comp.push("cavalry");
    if (strength >= 4) comp.push("pike");
    return comp.map((type, i) => ({ type, r: ENEMY_SLOTS[i].r, c: ENEMY_SLOTS[i].c }));
  }

  /** 国の強さから、既存の陣形バトルエンジンにそのまま渡せるステージを動的生成する */
  function generateProvinceBattleStage(province) {
    const strength = Math.min(4, Math.max(1, province.strength || 1));
    return {
      id: `conquest-${province.id}`,
      type: "field",
      name: `${province.name}攻め`,
      description: `${province.name}を治める勢力との合戦。`,
      cols: 7,
      rows: 6,
      terrain: STANDARD_TERRAIN,
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: buildEnemyComposition(strength),
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    };
  }

  window.KG.provinces = { PROVINCES, createProvinceInstances, generateProvinceBattleStage };
})();
