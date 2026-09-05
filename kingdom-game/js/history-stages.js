// 歴史編: 実在の合戦を再現するステージ集（戦国時代の代表的な合戦を年代順に収録）。
// 地名・武将名は史実（著作権上の配慮は不要）。スキーマは stages.js の STAGES と同じ。
// 追加で `history`（解説文）を持つ。

(function () {
  window.KG = window.KG || {};

  const P = "plain";
  const H = "hill";
  const F = "forest";
  const R = "river";

  const STANDARD6 = [
    [P, P, H, P, H, P, P],
    [P, F, P, P, P, F, P],
    [P, P, P, P, P, P, P],
    [P, H, P, P, P, H, P],
    [P, P, P, P, P, P, P],
    [P, P, P, P, P, P, P],
  ];

  const HISTORY_STAGES = [
    {
      id: "kawagoe",
      type: "field",
      name: "河越城の戦い",
      description: "夜襲で大軍の包囲を破れ。日本三大奇襲の一つ。",
      history:
        "1546年、関東の覇権を巡る河越城の攻防で、北条氏康はわずかな手勢で城を包囲する扇谷上杉・" +
        "山内上杉・古河公方の連合軍に夜襲を仕掛けた。奇襲は成功し、寡兵の北条方が大軍を打ち破ったと" +
        "伝わる。日本三大奇襲の一つに数えられる。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [F, P, F, P, F, P, F],
        [F, F, P, P, P, F, F],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 1 },
        { type: "infantry", r: 2, c: 3 },
        { type: "infantry", r: 2, c: 5 },
        { type: "archer", r: 1, c: 2 },
        { type: "pike", r: 1, c: 4 },
      ],
      startCost: 5,
      costPerTurn: 2,
      maxCost: 12,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: 10,
    },
    {
      id: "okehazama",
      type: "field",
      name: "桶狭間の戦い",
      description: "寡兵で大軍を打ち破れ。奇襲がものを言う一戦。",
      history:
        "1560年、駿河の今川義元が大軍を率いて尾張に侵攻した。迎え撃つ織田信長の兵力はわずか。" +
        "世間は今川優勢と見ていたが、信長は奇襲によって義元の本陣を強襲し、劣勢を覆して大勝利を" +
        "収めたと伝えられる。寡兵が大軍を破った合戦として広く知られている。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [F, F, P, F, F, P, P],
        [F, P, P, P, P, F, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 1 },
        { type: "infantry", r: 2, c: 3 },
        { type: "infantry", r: 2, c: 5 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 1, c: 5 },
      ],
      startCost: 5,
      costPerTurn: 2,
      maxCost: 12,
      allowedUnits: ["infantry", "archer", "cavalry", "pike", "nobunaga"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: 10,
    },
    {
      id: "kawanakajima",
      type: "field",
      name: "川中島の戦い",
      description: "拮抗した大軍同士の激突。川を挟んだ攻防を制せ。",
      history:
        "1550年代から60年代にかけて、甲斐の武田信玄と越後の上杉謙信は北信濃の領有をめぐって幾度も" +
        "激突した。中でも1561年の戦いは最も激しかったと伝わり、川に囲まれた中島の地で両軍が" +
        "一進一退の攻防を繰り広げたとされる。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [P, P, P, P, P, P, P],
        [R, R, R, R, R, R, R],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 1, c: 2 },
        { type: "infantry", r: 1, c: 4 },
        { type: "archer", r: 0, c: 4 },
        { type: "cavalry", r: 1, c: 3 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "anegawa",
      type: "field",
      name: "姉川の戦い",
      description: "川を挟んだ連合軍同士の激戦。",
      history:
        "1570年、織田信長・徳川家康の連合軍と、浅井長政・朝倉義景の連合軍が近江の姉川で激突した。" +
        "両軍入り乱れる激戦の末、織田・徳川方が勝利し、信長包囲網の一角を崩したとされる。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [P, P, P, P, P, P, P],
        [R, R, R, R, R, R, R],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 1, c: 1 },
        { type: "infantry", r: 1, c: 5 },
        { type: "archer", r: 0, c: 5 },
        { type: "cavalry", r: 1, c: 3 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "mikatagahara",
      type: "field",
      name: "三方ヶ原の戦い",
      description: "武田の大軍に挑む、圧倒的不利な一戦。",
      history:
        "1572年、上洛を目指す武田信玄の大軍が遠江に侵攻すると、徳川家康は浜松城から打って出て" +
        "三方ヶ原で迎え撃った。だが兵力差は大きく、家康は生涯最大の敗北を喫したと伝わる。この経験は" +
        "後の慎重な戦略に影響したとされる。",
      cols: 7,
      rows: 6,
      terrain: [
        [H, P, H, P, H, P, H],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 2 },
        { type: "infantry", r: 2, c: 4 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 1, c: 1 },
        { type: "cavalry", r: 1, c: 5 },
      ],
      startCost: 5,
      costPerTurn: 2,
      maxCost: 12,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "nagashino",
      type: "field",
      name: "長篠の戦い",
      description: "馬防柵と鉄砲で騎馬隊を迎え撃て。",
      history:
        "1575年、織田信長・徳川家康の連合軍は設楽原に馬防柵を築き鉄砲隊を配して武田勝頼の騎馬隊を" +
        "迎え撃った。集中運用された鉄砲の威力が騎馬隊に大打撃を与え、連合軍が大勝したと伝わる。" +
        "日本の戦術史における転換点とされる合戦。",
      cols: 7,
      rows: 6,
      terrain: [
        [P, P, H, P, H, P, P],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
        [F, F, F, F, F, F, F],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "cavalry", r: 1, c: 2 },
        { type: "cavalry", r: 1, c: 4 },
        { type: "cavalry", r: 2, c: 3 },
        { type: "infantry", r: 2, c: 1 },
        { type: "archer", r: 2, c: 5 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "shizugatake",
      type: "field",
      name: "賤ヶ岳の戦い",
      description: "後継者争いを制する山岳戦。",
      history:
        "1582年の本能寺の変後、織田家の後継を巡り羽柴（豊臣）秀吉と柴田勝家が対立した。1583年、" +
        "近江賤ヶ岳で両軍が激突し秀吉方が勝利。これにより秀吉の天下取りが大きく前進したとされる。",
      cols: 7,
      rows: 6,
      terrain: [
        [H, P, H, P, H, P, H],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
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
        { type: "pike", r: 1, c: 1 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "komaki_nagakute",
      type: "field",
      name: "小牧・長久手の戦い",
      description: "秀吉方と家康方、局地戦の行方は。",
      history:
        "1584年、豊臣秀吉と、織田信雄・徳川家康の連合軍が尾張・美濃周辺で対峙した。膠着状態が" +
        "続く中、長久手での局地戦では家康方が打撃を与えたと伝わる。最終的には秀吉と信雄の和睦で" +
        "戦は終結した。",
      cols: 7,
      rows: 6,
      terrain: STANDARD6,
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 2 },
        { type: "infantry", r: 2, c: 4 },
        { type: "archer", r: 0, c: 5 },
        { type: "cavalry", r: 1, c: 3 },
        { type: "pike", r: 1, c: 1 },
      ],
      startCost: 6,
      costPerTurn: 2,
      maxCost: 14,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
    {
      id: "odawara",
      type: "siege",
      name: "小田原征伐",
      description: "難攻不落の城を落とし、天下統一を完成させよ。",
      history:
        "1590年、豊臣秀吉は関東の北条氏を屈服させるべく大軍で小田原城を包囲した。難攻不落と謳われた" +
        "城だったが、秀吉は周辺に一夜城を築くなど圧倒的な物量で対抗し、北条氏はついに降伏したと伝わる。" +
        "これにより秀吉の天下統一が完成したとされる。",
      cols: 7,
      rows: 7,
      terrain: [
        [P, P, P, P, P, P, P],
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
        { kind: "wall", r: 0, c: 0, hp: 45 },
        { kind: "tower", r: 0, c: 1, hp: 22, atk: 7, range: 3 },
        { kind: "wall", r: 0, c: 2, hp: 45 },
        { kind: "gate", r: 0, c: 3, hp: 38 },
        { kind: "wall", r: 0, c: 4, hp: 45 },
        { kind: "tower", r: 0, c: 5, hp: 22, atk: 7, range: 3 },
        { kind: "wall", r: 0, c: 6, hp: 45 },
      ],
      enemyUnits: [
        { type: "infantry", r: 2, c: 1 },
        { type: "infantry", r: 2, c: 5 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 2, c: 3 },
        { type: "pike", r: 1, c: 1 },
      ],
      startCost: 7,
      costPerTurn: 2,
      maxCost: 18,
      allowedUnits: ["infantry", "archer", "cavalry", "pike", "ram", "ladder"],
      winCondition: { type: "breachGate" },
      lossCondition: { type: "hqLost" },
      turnLimit: 16,
    },
    {
      id: "sekigahara",
      type: "field",
      name: "関ヶ原の戦い",
      description: "天下分け目の最終決戦。",
      history:
        "1600年、豊臣政権内の対立から、徳川家康率いる東軍と石田三成率いる西軍が美濃・関ヶ原で" +
        "激突した。合戦は東軍の勝利に終わり、徳川家康による天下統一・江戸開府への道が開かれた、" +
        "日本史上最大級の合戦と言われる。",
      cols: 7,
      rows: 6,
      terrain: [
        [H, P, H, P, H, P, H],
        [P, P, P, P, P, P, P],
        [P, F, P, P, P, F, P],
        [H, P, P, P, P, P, H],
        [P, P, P, P, P, P, P],
        [P, P, P, P, P, P, P],
      ],
      playerDeployRows: [4, 5],
      playerHQ: { r: 5, c: 3 },
      enemyHQ: { r: 0, c: 3 },
      enemyUnits: [
        { type: "infantry", r: 2, c: 2 },
        { type: "infantry", r: 2, c: 4 },
        { type: "archer", r: 1, c: 3 },
        { type: "cavalry", r: 1, c: 1 },
        { type: "cavalry", r: 1, c: 5 },
        { type: "pike", r: 3, c: 3 },
      ],
      startCost: 7,
      costPerTurn: 2,
      maxCost: 16,
      allowedUnits: ["infantry", "archer", "cavalry", "pike"],
      winCondition: { type: "defeatHQ" },
      lossCondition: { type: "hqLost" },
      turnLimit: null,
    },
  ];

  function getHistoryStageById(id) {
    return HISTORY_STAGES.find((s) => s.id === id) || null;
  }

  window.KG.historyStages = { HISTORY_STAGES, getHistoryStageById };
})();
