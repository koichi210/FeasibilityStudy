// 編成画面で使う「城・砦」データ。武将と同じく編成で選んでから戦闘に持ち込む、超高コストの特殊ユニット。
// move:0 なので一度置いたら動けない（既存の移動力ロジックがそのまま「動けない」を表現してくれる）。
// 実在の城名（史実）なので著作権上の配慮は不要。

(function () {
  window.KG = window.KG || {};

  const CASTLE_TYPES = {
    osaka: {
      id: "osaka", name: "大阪城", cost: 7, hp: 70, atk: 10, range: 2, move: 0,
      category: null, beatsCategory: null, defBonus: 5, icon: "🏯",
      isCastle: true,
    },
    sanadamaru: {
      id: "sanadamaru", name: "真田丸", cost: 7, hp: 50, atk: 12, range: 2, move: 0,
      category: null, beatsCategory: null, defBonus: 3, icon: "🏯",
      isCastle: true,
    },
    azuchi: {
      id: "azuchi", name: "安土城", cost: 7, hp: 60, atk: 9, range: 1, move: 0,
      category: null, beatsCategory: null, defBonus: 4, icon: "🏯",
      isCastle: true,
    },
    edo: {
      id: "edo", name: "江戸城", cost: 7, hp: 65, atk: 9, range: 1, move: 0,
      category: null, beatsCategory: null, defBonus: 5, icon: "🏯",
      isCastle: true,
    },
    toride: {
      id: "toride", name: "砦", cost: 7, hp: 40, atk: 8, range: 1, move: 0,
      category: null, beatsCategory: null, defBonus: 3, icon: "🚩",
      isCastle: true,
    },
  };

  window.KG.castles = { CASTLE_TYPES };
})();
