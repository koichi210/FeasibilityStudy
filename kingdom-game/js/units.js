// 兵種・攻城兵器・本陣のデータ定義。
// category: 三すくみ判定に使う分類（歩兵/騎兵/弓兵はここが噛み合うと1.5倍ダメージ）
// beatsCategory: このカテゴリを相手にすると有利
// siegeAtk: 城壁・城門を攻撃するときに atk の代わりに使う値（攻城兵器のみ）
// defBonus: 被ダメージから引かれる素の防御力

(function () {
  window.KG = window.KG || {};

  const UNIT_TYPES = {
    infantry: {
      id: "infantry", name: "歩兵", cost: 2, hp: 32, atk: 9, range: 1, move: 2,
      category: "infantry", beatsCategory: "cavalry", defBonus: 0, icon: "🛡️",
    },
    cavalry: {
      id: "cavalry", name: "騎兵", cost: 3, hp: 28, atk: 11, range: 1, move: 3,
      category: "cavalry", beatsCategory: "archer", defBonus: 0, icon: "🐎",
    },
    archer: {
      id: "archer", name: "弓兵", cost: 2, hp: 20, atk: 10, range: 2, move: 1,
      category: "archer", beatsCategory: "infantry", defBonus: 0, icon: "🏹",
    },
    pike: {
      id: "pike", name: "戟兵", cost: 3, hp: 38, atk: 8, range: 1, move: 1,
      category: "pike", beatsCategory: null, defBonus: 2, icon: "🗡️",
    },
  };

  // 攻城戦専用の兵器。対ユニット戦闘力は低いが、城壁・城門への siegeAtk が高い。
  const SIEGE_UNIT_TYPES = {
    ram: {
      id: "ram", name: "衝車", cost: 4, hp: 44, atk: 6, range: 1, move: 1,
      category: null, beatsCategory: null, defBonus: 1, siegeAtk: 20, icon: "🛠️",
    },
    ladder: {
      id: "ladder", name: "雲梯", cost: 3, hp: 24, atk: 7, range: 1, move: 1,
      category: null, beatsCategory: null, defBonus: 0, siegeAtk: 12, icon: "🪜",
    },
  };

  const HQ_TYPE = {
    id: "hq", name: "本陣", cost: 0, hp: 50, atk: 4, range: 1, move: 0,
    category: null, beatsCategory: null, defBonus: 2, icon: "🚩",
  };

  /**
   * 種別IDから定義を引く（兵種・攻城兵器・本陣・武将・城をまとめて検索）。
   * extraRegistries には HERO_TYPES / PREMIUM_HERO_TYPES / CASTLE_TYPES などを好きな数だけ渡せる。
   */
  function findUnitType(typeId, ...extraRegistries) {
    if (UNIT_TYPES[typeId]) return UNIT_TYPES[typeId];
    if (SIEGE_UNIT_TYPES[typeId]) return SIEGE_UNIT_TYPES[typeId];
    for (const registry of extraRegistries) {
      if (registry && registry[typeId]) return registry[typeId];
    }
    return typeId === HQ_TYPE.id ? HQ_TYPE : null;
  }

  window.KG.units = { UNIT_TYPES, SIEGE_UNIT_TYPES, HQ_TYPE, findUnitType };
})();
