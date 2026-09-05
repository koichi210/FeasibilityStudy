// 戦闘画面の描画と入力処理。DOM操作はすべてここに閉じ込める。

(function () {
  window.KG = window.KG || {};
  const { terrainAt, TERRAIN_INFO } = window.KG.board;
  const { STRUCTURE_KIND_INFO, getStructureAt } = window.KG.siege;
  const { findUnitType } = window.KG.units;
  const { HERO_TYPES, PREMIUM_HERO_TYPES } = window.KG.characters;
  const { CASTLE_TYPES } = window.KG.castles;
  const {
    getUnitById,
    getReachableCells,
    getAttackableTargets,
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
    pushLog,
  } = window.KG.battle;
  const { runEnemyTurn } = window.KG.ai;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** 「移動先 dest から攻撃したら何を狙えるか」を、実際に動かさずに調べる */
  function attackableFrom(state, unit, r, c) {
    const origR = unit.r;
    const origC = unit.c;
    unit.r = r;
    unit.c = c;
    const result = getAttackableTargets(state, unit);
    unit.r = origR;
    unit.c = origC;
    return result;
  }

  function mountBattleUI(root, state, onEnd) {
    let selection = null; // { unitId, mode: 'normal' | 'dash-move' | 'dash-attack', dest? }
    let pendingDeployType = null;
    let endNotified = false;

    function clearSelection() {
      selection = null;
      pendingDeployType = null;
    }

    function afterAction() {
      checkBattleEnd(state);
      clearSelection();
      render();
    }

    function handleEndTurn() {
      resetTurnFlags(state, "enemy");
      runEnemyTurn(state);
      const outcome = checkBattleEnd(state);
      if (!outcome) startNewTurn(state);
      clearSelection();
      render();
    }

    function handleHandCardClick(typeId) {
      if (state.phase !== "battle") return;
      clearSelection();
      pendingDeployType = typeId;
      render();
    }

    function handleUnitButtonClick(unit) {
      if (unit.ownerId !== "player" || unit.acted) return;
      pendingDeployType = null;
      selection = { unitId: unit.id, mode: "normal" };
      render();
    }

    function handleWait() {
      const unit = getUnitById(state, selection.unitId);
      if (!unit) return clearSelection();
      actionWait(state, unit);
      afterAction();
    }

    function handleSkillButton() {
      const unit = getUnitById(state, selection.unitId);
      if (!unit || !unit.skill || unit.skillUsed || unit.acted) return;
      if (unit.skill.id === "dash") {
        selection = { unitId: unit.id, mode: "dash-move" };
        render();
      } else if (unit.skill.id === "volley") {
        actionVolleySkill(state, unit);
        afterAction();
      }
    }

    function handleConfirmDashNoAttack() {
      const unit = getUnitById(state, selection.unitId);
      if (!unit || !selection.dest) return;
      actionDashSkill(state, unit, selection.dest.r, selection.dest.c, null);
      afterAction();
    }

    function handleCellClick(r, c) {
      if (state.phase !== "battle") return;
      // 配置モード
      if (pendingDeployType) {
        const result = deployUnit(state, pendingDeployType, r, c);
        if (result.ok) {
          pendingDeployType = null;
          afterAction();
        } else {
          pushLog(state, `配置できません: ${result.error}`);
          render();
        }
        return;
      }

      // 未選択なら、自軍ユニットのクリックだけを拾う
      if (!selection) {
        const unit = state.units.find((u) => u.r === r && u.c === c);
        if (unit) handleUnitButtonClick(unit);
        return;
      }

      const unit = getUnitById(state, selection.unitId);
      if (!unit) return clearSelection();

      if (selection.mode === "normal") {
        const reachable = getReachableCells(state, unit);
        const attackable = getAttackableTargets(state, unit);
        const targetUnit = attackable.units.find((u) => u.r === r && u.c === c);
        const targetStruct = attackable.structures.find((s) => s.r === r && s.c === c);
        if (targetUnit) {
          actionAttackUnit(state, unit, targetUnit);
          afterAction();
          return;
        }
        if (targetStruct) {
          actionAttackStructure(state, unit, targetStruct);
          afterAction();
          return;
        }
        if (reachable.has(`${r},${c}`)) {
          actionMove(state, unit, r, c);
          afterAction();
          return;
        }
        if (r === unit.r && c === unit.c) {
          clearSelection();
          render();
          return;
        }
        // 別の自軍ユニットに切り替え
        const other = state.units.find(
          (u) => u.r === r && u.c === c && u.ownerId === "player" && !u.acted
        );
        if (other) handleUnitButtonClick(other);
        return;
      }

      if (selection.mode === "dash-move") {
        const reachable = getReachableCells(state, unit);
        if (reachable.has(`${r},${c}`)) {
          selection = { unitId: unit.id, mode: "dash-attack", dest: { r, c } };
          render();
        }
        return;
      }

      if (selection.mode === "dash-attack") {
        const { dest } = selection;
        const preview = attackableFrom(state, unit, dest.r, dest.c);
        const targetUnit = preview.units.find((u) => u.r === r && u.c === c);
        const targetStruct = preview.structures.find((s) => s.r === r && s.c === c);
        if (targetUnit) {
          actionDashSkill(state, unit, dest.r, dest.c, { kind: "unit", unit: targetUnit });
          afterAction();
        } else if (targetStruct) {
          actionDashSkill(state, unit, dest.r, dest.c, {
            kind: "structure",
            structure: targetStruct,
          });
          afterAction();
        } else if (r === dest.r && c === dest.c) {
          handleConfirmDashNoAttack();
        }
        return;
      }
    }

    function buildStatusBar() {
      const bar = el("div", "status-bar");
      bar.appendChild(el("div", "status-item", `${state.stage.name}`));
      bar.appendChild(el("div", "status-item", `ターン ${state.turn}${state.stage.turnLimit ? ` / ${state.stage.turnLimit}` : ""}`));
      bar.appendChild(el("div", "status-item", `コスト ${state.cost} / ${state.maxCost}`));

      const playerHQ = state.units.find((u) => u.ownerId === "player" && u.isHQ);
      if (playerHQ) {
        bar.appendChild(el("div", "status-item", `自軍本陣 HP ${playerHQ.hp}/${playerHQ.maxHp}`));
      }
      if (state.stage.type === "field") {
        const enemyHQ = state.units.find((u) => u.ownerId === "enemy" && u.isHQ);
        bar.appendChild(
          el("div", "status-item", enemyHQ ? `敵本陣 HP ${enemyHQ.hp}/${enemyHQ.maxHp}` : "敵本陣 撃破！")
        );
      } else {
        const gate = state.structures.find((s) => s.kind === "gate");
        bar.appendChild(
          el("div", "status-item", gate ? `城門 HP ${gate.hp}/${gate.maxHp}` : "城門 突破！")
        );
      }
      return bar;
    }

    function buildBoard() {
      const boardEl = el("div", "board");
      boardEl.style.gridTemplateColumns = `repeat(${state.board.cols}, 1fr)`;

      let reachableSet = new Map();
      let attackableUnits = [];
      let attackableStructs = [];
      let selectedCell = null;

      if (selection) {
        const unit = getUnitById(state, selection.unitId);
        if (unit) {
          if (selection.mode === "normal") {
            reachableSet = getReachableCells(state, unit);
            const atk = getAttackableTargets(state, unit);
            attackableUnits = atk.units;
            attackableStructs = atk.structures;
            selectedCell = { r: unit.r, c: unit.c };
          } else if (selection.mode === "dash-move") {
            reachableSet = getReachableCells(state, unit);
            selectedCell = { r: unit.r, c: unit.c };
          } else if (selection.mode === "dash-attack") {
            const atk = attackableFrom(state, unit, selection.dest.r, selection.dest.c);
            attackableUnits = atk.units;
            attackableStructs = atk.structures;
            selectedCell = selection.dest;
          }
        }
      }

      for (let r = 0; r < state.board.rows; r += 1) {
        for (let c = 0; c < state.board.cols; c += 1) {
          const cell = el("button", "cell");
          const terrain = terrainAt(state.board, r, c);
          cell.classList.add(`terrain-${terrain}`);

          if (state.stage.playerDeployRows.includes(r)) cell.classList.add("deploy-zone");
          if (pendingDeployType) {
            const blocked =
              state.units.some((u) => u.r === r && u.c === c) ||
              state.structures.some((s) => s.r === r && s.c === c && s.hp > 0);
            if (state.stage.playerDeployRows.includes(r) && !blocked) {
              cell.classList.add("cell-deployable");
            }
          }
          if (reachableSet.has(`${r},${c}`)) cell.classList.add("cell-reachable");
          if (attackableUnits.some((u) => u.r === r && u.c === c)) cell.classList.add("cell-attackable");
          if (attackableStructs.some((s) => s.r === r && s.c === c)) cell.classList.add("cell-attackable");
          if (selectedCell && selectedCell.r === r && selectedCell.c === c) {
            cell.classList.add("cell-selected");
          }

          const unit = state.units.find((u) => u.r === r && u.c === c);
          const structure = !unit ? getStructureAt(state.structures, r, c) : null;

          if (unit) {
            cell.classList.add(unit.ownerId === "player" ? "owner-player" : "owner-enemy");
            if (unit.ownerId === "player" && unit.acted) cell.classList.add("cell-acted");
            const icon = el("div", "unit-icon", unit.icon);
            cell.appendChild(icon);
            const hpWrap = el("div", "hp-bar");
            const hpFill = el("div", "hp-fill");
            hpFill.style.width = `${Math.max(0, (unit.hp / unit.maxHp) * 100)}%`;
            hpWrap.appendChild(hpFill);
            cell.appendChild(hpWrap);
            cell.title = `${unit.name} HP${unit.hp}/${unit.maxHp} 攻${unit.atk}`;
          } else if (structure && structure.hp > 0) {
            cell.classList.add("structure", `structure-${structure.kind}`);
            const info = STRUCTURE_KIND_INFO[structure.kind];
            cell.appendChild(el("div", "unit-icon", info.icon));
            const hpWrap = el("div", "hp-bar");
            const hpFill = el("div", "hp-fill");
            hpFill.style.width = `${Math.max(0, (structure.hp / structure.maxHp) * 100)}%`;
            hpWrap.appendChild(hpFill);
            cell.appendChild(hpWrap);
            cell.title = `${info.name} HP${structure.hp}/${structure.maxHp}`;
          } else {
            const info = TERRAIN_INFO[terrain];
            if (info.icon) cell.appendChild(el("div", "terrain-icon", info.icon));
          }

          cell.addEventListener("click", () => handleCellClick(r, c));
          boardEl.appendChild(cell);
        }
      }
      return boardEl;
    }

    function buildHand() {
      const hand = el("div", "hand");
      hand.appendChild(el("div", "panel-title", "配置できるユニット"));
      const list = el("div", "hand-list");
      for (const typeId of state.stage.allowedUnits) {
        const type = findUnitType(typeId, HERO_TYPES, PREMIUM_HERO_TYPES, CASTLE_TYPES);
        if (!type) continue;
        const card = el("button", "hand-card");
        if (pendingDeployType === typeId) card.classList.add("selected");
        if (state.cost < type.cost) card.classList.add("disabled");
        card.appendChild(el("div", "unit-icon", type.icon));
        card.appendChild(el("div", "hand-name", type.name));
        card.appendChild(el("div", "hand-cost", `コスト ${type.cost}`));
        card.addEventListener("click", () => {
          if (state.cost < type.cost) return;
          handleHandCardClick(typeId);
        });
        list.appendChild(card);
      }
      hand.appendChild(list);
      return hand;
    }

    function buildSelectedPanel() {
      const panel = el("div", "selected-panel");
      if (!selection) {
        panel.appendChild(el("div", "panel-title", "ユニットを選択してください"));
        return panel;
      }
      const unit = getUnitById(state, selection.unitId);
      if (!unit) return panel;

      panel.appendChild(el("div", "panel-title", `${unit.icon} ${unit.name}`));
      panel.appendChild(
        el("div", "unit-stats", `HP ${unit.hp}/${unit.maxHp}　攻撃 ${unit.atk}　射程 ${unit.range}　移動 ${unit.move}`)
      );

      if (selection.mode === "dash-move") {
        panel.appendChild(el("div", "hint-text", "移動先のマスを選んでください"));
      } else if (selection.mode === "dash-attack") {
        panel.appendChild(el("div", "hint-text", "攻撃対象を選ぶか、同じマスをもう一度押すと移動だけで終了します"));
      }

      const buttons = el("div", "action-buttons");

      if (selection.mode === "normal") {
        const waitBtn = el("button", "action-btn", "待機");
        waitBtn.addEventListener("click", handleWait);
        buttons.appendChild(waitBtn);

        if (unit.skill && !unit.skillUsed) {
          const skillBtn = el("button", "action-btn skill-btn", `${unit.skill.name}`);
          skillBtn.title = unit.skill.desc;
          skillBtn.addEventListener("click", handleSkillButton);
          buttons.appendChild(skillBtn);
        }
      }

      const cancelBtn = el("button", "action-btn cancel-btn", "キャンセル");
      cancelBtn.addEventListener("click", () => {
        clearSelection();
        render();
      });
      buttons.appendChild(cancelBtn);

      panel.appendChild(buttons);
      return panel;
    }

    function buildLog() {
      const log = el("div", "log-panel");
      log.appendChild(el("div", "panel-title", "戦況ログ"));
      const list = el("div", "log-list");
      for (const line of state.log.slice(-10)) {
        list.appendChild(el("div", "log-line", line));
      }
      log.appendChild(list);
      return log;
    }

    function buildFooter() {
      const footer = el("div", "footer-bar");
      const endBtn = el("button", "end-turn-btn", "ターン終了");
      endBtn.disabled = state.phase !== "battle";
      endBtn.addEventListener("click", handleEndTurn);
      footer.appendChild(endBtn);
      return footer;
    }

    function buildEndOverlay() {
      if (!state.outcome) return null;
      const overlay = el("div", "end-overlay");
      const box = el("div", "end-box");
      box.appendChild(el("div", "end-title", state.outcome === "win" ? "勝利！" : "敗北…"));
      const btn = el("button", "action-btn", "結果を見る");
      btn.addEventListener("click", () => {
        if (!endNotified) {
          endNotified = true;
          onEnd(state.outcome);
        }
      });
      box.appendChild(btn);
      overlay.appendChild(box);
      return overlay;
    }

    function render() {
      root.innerHTML = "";
      root.appendChild(buildStatusBar());

      const main = el("div", "battle-main");
      main.appendChild(buildBoard());

      const side = el("div", "battle-side");
      side.appendChild(buildSelectedPanel());
      side.appendChild(buildHand());
      side.appendChild(buildLog());
      main.appendChild(side);

      root.appendChild(main);
      root.appendChild(buildFooter());

      const overlay = buildEndOverlay();
      if (overlay) root.appendChild(overlay);
    }

    render();
  }

  window.KG.ui = { mountBattleUI };
})();
