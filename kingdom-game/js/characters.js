// 武将（固有スキル持ちユニット）データ。
// ※ hakuoh/gengai（中華編）はオリジナル名。nobunaga（歴史編）は実在の人物名。README.md の注意書き参照。
//
// skill.id で battle.js 側の分岐を判定する:
//   "dash"   … 移動してからその場で追加攻撃できる（1戦につき1回）
//   "volley" … 射程内の敵全員に一斉射撃（威力6割・1戦につき1回）

(function () {
  window.KG = window.KG || {};

  const HERO_TYPES = {
    hakuoh: {
      id: "hakuoh", name: "白央", cost: 3, hp: 34, atk: 11, range: 1, move: 2,
      category: "infantry", beatsCategory: "cavalry", defBonus: 0, icon: "⚡",
      isHero: true,
      skill: { id: "dash", name: "疾駆", desc: "移動した直後、もう一度攻撃できる" },
    },
    gengai: {
      id: "gengai", name: "玄凱", cost: 4, hp: 24, atk: 9, range: 3, move: 1,
      category: "archer", beatsCategory: "infantry", defBonus: 0, icon: "🎯",
      isHero: true,
      skill: { id: "volley", name: "遠矢の陣", desc: "射程内の敵全員に一斉射撃（威力6割）" },
    },
    // 歴史編「桶狭間の戦い」専用。実在の武将名（史実の人物のため名称そのままでOK）。
    nobunaga: {
      id: "nobunaga", name: "織田信長", cost: 3, hp: 30, atk: 12, range: 1, move: 2,
      category: "infantry", beatsCategory: "cavalry", defBonus: 0, icon: "🔥",
      isHero: true,
      skill: { id: "dash", name: "奇襲", desc: "移動した直後、もう一度攻撃できる" },
    },
  };

  // 編成画面で選んで持ち込む、超高コストの実在武将。実在の人物のため名称そのままでOK。
  const PREMIUM_HERO_TYPES = {
    hideyoshi: {
      id: "hideyoshi", name: "豊臣秀吉", cost: 7, hp: 48, atk: 14, range: 1, move: 2,
      category: "infantry", beatsCategory: "cavalry", defBonus: 1, icon: "👑",
      isHero: true,
      skill: { id: "volley", name: "太閤の采配", desc: "射程内の敵全員に一斉射撃（威力6割）" },
    },
    yukimura: {
      id: "yukimura", name: "真田幸村", cost: 7, hp: 42, atk: 16, range: 1, move: 3,
      category: "cavalry", beatsCategory: "archer", defBonus: 0, icon: "🔴",
      isHero: true,
      skill: { id: "dash", name: "真田の突撃", desc: "移動した直後、もう一度攻撃できる" },
    },
    masamune: {
      id: "masamune", name: "伊達政宗", cost: 7, hp: 40, atk: 15, range: 1, move: 3,
      category: "infantry", beatsCategory: "cavalry", defBonus: 0, icon: "🐉",
      isHero: true,
      skill: { id: "dash", name: "独眼竜の疾風", desc: "移動した直後、もう一度攻撃できる" },
    },
    shingen: {
      id: "shingen", name: "武田信玄", cost: 7, hp: 50, atk: 13, range: 1, move: 2,
      category: "cavalry", beatsCategory: "archer", defBonus: 1, icon: "⛰️",
      isHero: true,
      skill: { id: "volley", name: "風林火山の采配", desc: "射程内の敵全員に一斉射撃（威力6割）" },
    },
    kenshin: {
      id: "kenshin", name: "上杉謙信", cost: 7, hp: 45, atk: 15, range: 1, move: 2,
      category: "archer", beatsCategory: "infantry", defBonus: 0, icon: "⚔️",
      isHero: true,
      skill: { id: "dash", name: "車懸りの陣", desc: "移動した直後、もう一度攻撃できる" },
    },
  };

  window.KG.characters = { HERO_TYPES, PREMIUM_HERO_TYPES };
})();
