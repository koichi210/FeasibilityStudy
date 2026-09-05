// 戦闘の中核ロジック。野戦・攻城戦の両方がこの上で動く。
// UI（ui.js）や AI（ai.js）はここに定義した関数を通じてのみ盤面を変更する。

(function () {
  window.KG = window.KG || {};
  const { uid, manhattan } = window.KG.util;
  const { HQ_TYPE, findUnitType } = window.KG.units;
  const { HERO_TYPES, PREMIUM_HERO_TYPES } = window.KG.characters;
  const { CASTLE_TYPES } = window.KG.castles;
  const { createBoard, terrainAt, terrainInfoAt, computeReachable } = window.KG.board;
  const { createStructures, siegeDamageOf, STRUCTURE_KIND_INFO } = window.KG.siege;

  /** 兵種・攻城兵器・本陣・武将（通常/編成）・城をまとめて検索する */
  function resolveUnitType(typeId) {
    return findUnitType(typeId, HERO_TYPES, PREMIUM_HERO_TYPES, CASTLE_TYPES);
  }

  function createUnitInstance(type, ownerId, r, c) {
    return {
      id: uid("u"),
      ownerId,
      typeId: type.id,
      name: type.name,
      icon: type.icon,
      category: type.category,
      beatsCategory: type.beatsCategory,
      atk: type.atk,
      hp: type.hp,
      maxHp: type.hp,
      range: type.range,
      move: type.move,
      defBonus: type.defBonus || 0,
      siegeAtk: type.siegeAtk || 0,
      r,
      c,
      acted: false,
      isHQ: type.id === "hq",
      isHero: !!type.isHero,
      isCastle: !!type.isCastle,
      skill: type.skill ? { ...type.skill } : null,
      skillUsed: false,
    };
  }

  function pushLog(state, message) {
    state.log.push(message);
    if (state.log.length > 40) state.log.shift();
  }

  function createBattleState(stage) {
    const board = createBoard(stage);
    const units = [];

    units.push(createUnitInstance(HQ_TYPE, "player", stage.playerHQ.r, stage.playerHQ.c));
    if (stage.type === "field") {
      units.push(createUnitInstance(HQ_TYPE, "enemy", stage.enemyHQ.r, stage.enemyHQ.c));
    }
    for (const eu of stage.enemyUnits) {
      const type = resolveUnitType(eu.type);
      if (!type) continue;
      units.push(createUnitInstance(type, "enemy", eu.r, eu.c));
    }

    const structures = stage.type === "siege" ? createStructures(stage.structures) : [];

    return {
      stage,
      board,
      units,
      structures,
      cost: stage.startCost,
      maxCost: stage.maxCost || 99,
      turn: 1,
      phase: "battle", // 'battle' | 'ended'
      outcome: null, // null | 'win' | 'lose'
      log: [`${stage.name} 開戦！`],
    };
  }

  function getUnitAt(state, r, c) {
    return state.units.find((u) => u.r === r && u.c === c) || null;
  }

  function getUnitById(state, id) {
    return state.units.find((u) => u.id === id) || null;
  }

  function isCellBlocked(state, r, c) {
    if (state.units.some((u) => u.r === r && u.c === c)) return true;
    if (state.structures.some((s) => s.r === r && s.c === c && s.hp > 0)) return true;
    return false;
  }

  function getReachableCells(state, unit) {
    return computeReachable(state.board, unit.r, unit.c, unit.move, (r, c) =>
      isCellBlocked(state, r, c)
    );
  }

  /** その場から攻撃できる敵ユニット／構造物を求める（森にいる弓兵は射程+1） */
  function getAttackableTargets(state, unit) {
    let effRange = unit.range;
    const terrain = terrainAt(state.board, unit.r, unit.c);
    if (terrain === "forest" && unit.category === "archer") {
      effRange += terrainInfoAt(state.board, unit.r, unit.c).rangeBonus;
    }
    const units = state.units.filter(
      (u) => u.ownerId !== unit.ownerId && manhattan(unit.r, unit.c, u.r, u.c) <= effRange
    );
    const structures =
      unit.ownerId === "player"
        ? state.structures.filter(
            (s) => s.hp > 0 && manhattan(unit.r, unit.c, s.r, s.c) <= effRange
          )
        : [];
    return { units, structures };
  }

  /** ダメージ計算。attackerLike は {atk, beatsCategory} を持つオブジェクトなら何でもよい（矢櫓も可） */
  function computeDamage(attackerLike, defender, board, multiplier = 1) {
    let dmg = attackerLike.atk;
    if (
      attackerLike.beatsCategory &&
      defender.category &&
      attackerLike.beatsCategory === defender.category
    ) {
      dmg = Math.round(dmg * 1.5);
    }
    const terrain = terrainInfoAt(board, defender.r, defender.c);
    dmg -= terrain.defenseBonus;
    dmg -= defender.defBonus || 0;
    dmg = Math.round(dmg * multiplier);
    return Math.max(1, dmg);
  }

  function applyDamageToUnit(state, defender, dmg, attackerName) {
    defender.hp = Math.max(0, defender.hp - dmg);
    pushLog(state, `${attackerName}の攻撃！ ${defender.name}に${dmg}ダメージ`);
    if (defender.hp <= 0) {
      state.units = state.units.filter((u) => u.id !== defender.id);
      pushLog(state, `${defender.name}を撃破した！`);
    }
  }

  function attackStructureRaw(state, attacker, structure) {
    const dmg = siegeDamageOf(attacker);
    structure.hp = Math.max(0, structure.hp - dmg);
    const kindName = STRUCTURE_KIND_INFO[structure.kind].name;
    pushLog(state, `${attacker.name}が${kindName}に${dmg}ダメージ！`);
    if (structure.hp <= 0) {
      pushLog(state, `${kindName}が崩れた！`);
    }
  }

  // ---- プレイヤー操作（配置・移動・攻撃・待機・スキル） ----

  function deployUnit(state, typeId, r, c) {
    if (!state.stage.allowedUnits.includes(typeId)) {
      return { ok: false, error: "このステージでは使えない兵種です" };
    }
    const type = resolveUnitType(typeId);
    if (!type) return { ok: false, error: "不明な兵種です" };
    if (state.cost < type.cost) return { ok: false, error: "コストが足りません" };
    if (!state.stage.playerDeployRows.includes(r)) {
      return { ok: false, error: "自軍の配置エリアではありません" };
    }
    if (isCellBlocked(state, r, c)) return { ok: false, error: "そのマスには配置できません" };

    const unit = createUnitInstance(type, "player", r, c);
    state.units.push(unit);
    state.cost -= type.cost;
    pushLog(state, `${unit.name}を配置した。`);
    return { ok: true, unit };
  }

  function actionMove(state, unit, r, c) {
    unit.r = r;
    unit.c = c;
    unit.acted = true;
    pushLog(state, `${unit.name}が移動した。`);
  }

  function actionAttackUnit(state, attacker, defender) {
    const dmg = computeDamage(attacker, defender, state.board);
    applyDamageToUnit(state, defender, dmg, attacker.name);
    attacker.acted = true;
  }

  function actionAttackStructure(state, attacker, structure) {
    attackStructureRaw(state, attacker, structure);
    attacker.acted = true;
  }

  function actionWait(state, unit) {
    unit.acted = true;
    pushLog(state, `${unit.name}は待機した。`);
  }

  /** 白央「疾駆」: 移動してから、その場でもう一度攻撃する */
  function actionDashSkill(state, unit, destR, destC, target) {
    unit.r = destR;
    unit.c = destC;
    if (target) {
      if (target.kind === "unit") {
        const dmg = computeDamage(unit, target.unit, state.board);
        applyDamageToUnit(state, target.unit, dmg, unit.name);
      } else {
        attackStructureRaw(state, unit, target.structure);
      }
    }
    unit.skillUsed = true;
    unit.acted = true;
    pushLog(state, `${unit.name}が「疾駆」を発動！`);
  }

  /** 玄凱「遠矢の陣」: 射程内の敵全員に威力6割の一斉射撃 */
  function actionVolleySkill(state, unit) {
    const { units } = getAttackableTargets(state, unit);
    for (const target of units) {
      const dmg = computeDamage(unit, target, state.board, 0.6);
      applyDamageToUnit(state, target, dmg, unit.name);
    }
    unit.skillUsed = true;
    unit.acted = true;
    pushLog(state, `${unit.name}が「遠矢の陣」を発動！`);
  }

  // ---- ターン管理 ----

  function resetTurnFlags(state, ownerId) {
    state.units.filter((u) => u.ownerId === ownerId).forEach((u) => (u.acted = false));
  }

  function startNewTurn(state) {
    state.turn += 1;
    state.cost = Math.min(state.maxCost, state.cost + state.stage.costPerTurn);
    resetTurnFlags(state, "player");
    pushLog(state, `--- ターン${state.turn} ---`);
  }

  function checkBattleEnd(state) {
    if (state.outcome) return state.outcome;
    const stage = state.stage;

    if (stage.lossCondition.type === "hqLost") {
      const alive = state.units.some((u) => u.ownerId === "player" && u.isHQ);
      if (!alive) {
        state.outcome = "lose";
        state.phase = "ended";
        pushLog(state, "本陣が落ちた…敗北。");
        return state.outcome;
      }
    }
    if (stage.turnLimit && state.turn > stage.turnLimit) {
      state.outcome = "lose";
      state.phase = "ended";
      pushLog(state, "制限ターンに達した…敗北。");
      return state.outcome;
    }

    if (stage.winCondition.type === "defeatHQ") {
      const alive = state.units.some((u) => u.ownerId === "enemy" && u.isHQ);
      if (!alive) {
        state.outcome = "win";
        state.phase = "ended";
        pushLog(state, "敵本陣を撃破！勝利！");
        return state.outcome;
      }
    }
    if (stage.winCondition.type === "breachGate") {
      const gate = state.structures.find((s) => s.kind === "gate");
      if (!gate || gate.hp <= 0) {
        state.outcome = "win";
        state.phase = "ended";
        pushLog(state, "城門を突破した！勝利！");
        return state.outcome;
      }
    }
    return null;
  }

  window.KG.battle = {
    pushLog,
    createBattleState,
    getUnitAt,
    getUnitById,
    isCellBlocked,
    getReachableCells,
    getAttackableTargets,
    computeDamage,
    applyDamageToUnit,
    deployUnit,
    actionMove,
    actionAttackUnit,
    actionAttackStructure,
    actionWait,
    actionDashSkill,
    actionVolleySkill,
    resetTurnFlags,
    startNewTurn,
    checkBattleEnd,
  };
})();
