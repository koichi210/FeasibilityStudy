// ステージ定義。地名・敵将の名前もすべてオリジナル。

(function () {
  window.KG = window.KG || {};

  const P = "plain";
  const H = "hill";
  const F = "forest";
  const R = "river";

  const STAGES = [
    {
      id: "field1",
      type: "field",
      name: "蟻ヶ原の初陣",
      description:
        "河川を挟んだ平原での野戦。三すくみと地形を読んで、敵本陣を突き崩せ。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [P, F, P, P, P, F, P],
        [P, P, R, R, R, P, P],
        [P, H, P, P, P, H, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 1 },
        { type: "infantry", r: 2, c: 5 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 2, c: 3 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike", "hakuoh"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "siege1",
      type: "siege",
      name: "朱鷺口の城攻め",
      description:
        "城門を落とせば勝ち。矢櫓の射程に注意しつつ、衝車・雲梯で城壁に取り付け。",
      cols: 7,
      rows: 7,
      terrain: [
        [P, P, P, P, P, P, P], // 城壁ライン（構造物側で管理）
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, H, P, P, P, H, P],
        [F, P, P, P, P, P, F],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [5, 6],
      playerHQ: { r: 6, c: 3 },
      structures: [
        { kind: "wall", r: 0, c: 0, hp: 40 },
        { kind: "tower", r: 0, c: 1, hp: 20, atk: 7, range: 3 },
        { kind: "wall", r: 0, c: 2, hp: 40 },
        { kind: "gate", r: 0, c: 3, hp: 34 },
        { kind: "wall", r: 0, c: 4, hp: 40 },
        { kind: "tower", r: 0, c: 5, hp: 20, atk: 7, range: 3 },
        { kind: "wall", r: 0, c: 6, hp: 40 },
      ],
      enemyUnits: [
        { type: "infantry", r: 2, c: 1 },
        { type: "infantry", r: 2, c: 5 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 2, c: 3 },
      ],
      startCost: 7,
      costPerTurn: 2,
      maxCost: 16,
      allowedUnits: ["infantry", "archer", "cavalry", "pike", "ram", "ladder", "gengai"],
      winCondition: { type: "breachGate" },
      lossCondition: { type: "hqLost" },
      turnLimit: 14,
    },
  ];

  function getStageById(id) {
    return STAGES.find((s) => s.id === id) || null;
  }

  window.KG.stages = { STAGES, getStageById };
})();
