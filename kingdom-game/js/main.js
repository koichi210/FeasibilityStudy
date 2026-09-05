// 画面遷移の起点。タイトル → (中華編/歴史編ステージ選択 → 戦闘 → リザルト) / (国盗り編地図 → 戦闘 → 地図)。

(function () {
  const { STAGES, getStageById } = window.KG.stages;
  const { HISTORY_STAGES, getHistoryStageById } = window.KG.historyStages;
  const { createBattleState } = window.KG.battle;
  const { mountBattleUI } = window.KG.ui;
  const { isStageCleared, markStageCleared } = window.KG.save;
  const { generateProvinceBattleStage } = window.KG.provinces;
  const { createConquestState, resolveConquerResult } = window.KG.conquest;
  const { mountConquestUI } = window.KG.conquestUi;
  const { getEquippedIds } = window.KG.roster;
  const { mountFormationUI } = window.KG.formationUi;

  const screens = {
    title: document.getElementById("screen-title"),
    stageSelect: document.getElementById("screen-stage-select"),
    historyBrief: document.getElementById("screen-history-brief"),
    conquest: document.getElementById("screen-conquest"),
    formation: document.getElementById("screen-formation"),
    battle: document.getElementById("screen-battle"),
    result: document.getElementById("screen-result"),
  };

  /** 編成画面で選んだ武将・城を、ステージ本来のallowedUnitsに合流させたコピーを作る */
  function withRoster(stage) {
    const combined = new Set([...(stage.allowedUnits || []), ...getEquippedIds()]);
    return { ...stage, allowedUnits: Array.from(combined) };
  }

  function showScreen(name) {
    for (const key of Object.keys(screens)) {
      screens[key].hidden = key !== name;
    }
  }

  // ---- 中華編 / 歴史編（手書きステージのステージ選択・戦闘・リザルト） ----

  let currentStagesForSelect = STAGES;

  function renderStageSelect() {
    const list = document.getElementById("stage-list");
    list.innerHTML = "";
    const stagesForSelect = currentStagesForSelect;
    stagesForSelect.forEach((stage, index) => {
      const prevStage = stagesForSelect[index - 1];
      const locked = index > 0 && prevStage && !isStageCleared(prevStage.id);

      const card = document.createElement("button");
      card.className = "stage-card" + (locked ? " locked" : "");

      const name = document.createElement("div");
      name.className = "stage-name";
      name.textContent = stage.name;
      card.appendChild(name);

      const desc = document.createElement("div");
      desc.className = "stage-desc";
      desc.textContent = stage.description;
      card.appendChild(desc);

      const tag = document.createElement("div");
      tag.className = "stage-tag";
      const typeLabel = stage.type === "field" ? "野戦" : "攻城戦";
      tag.textContent = locked
        ? `${typeLabel} ・ 前のステージをクリアすると解放`
        : `${typeLabel}${isStageCleared(stage.id) ? " ・ クリア済み" : ""}`;
      card.appendChild(tag);

      if (locked) {
        card.disabled = true;
      } else {
        card.addEventListener("click", () => {
          if (stage.history) {
            showHistoryBrief(stage);
          } else {
            startStage(stage.id);
          }
        });
      }
      list.appendChild(card);
    });
  }

  function findStageAnywhere(stageId) {
    return getStageById(stageId) || getHistoryStageById(stageId);
  }

  function startStage(stageId) {
    const rawStage = findStageAnywhere(stageId);
    if (!rawStage) return;
    const stage = withRoster(rawStage);
    const state = createBattleState(stage);
    const battleRoot = document.getElementById("battle-root");
    showScreen("battle");
    mountBattleUI(battleRoot, state, (outcome) => {
      if (outcome === "win") markStageCleared(stageId);
      showResult(stage, outcome);
    });
  }

  function showResult(stage, outcome) {
    showScreen("result");
    const box = document.getElementById("result-box");
    box.innerHTML = "";

    const title = document.createElement("div");
    title.className = "result-title";
    title.textContent = outcome === "win" ? `${stage.name}　クリア！` : `${stage.name}　敗北…`;
    box.appendChild(title);

    const retryBtn = document.createElement("button");
    retryBtn.className = "action-btn";
    retryBtn.textContent = "もう一度挑戦";
    retryBtn.addEventListener("click", () => startStage(stage.id));
    box.appendChild(retryBtn);

    const backBtn = document.createElement("button");
    backBtn.className = "action-btn";
    backBtn.textContent = "ステージ選択へ";
    backBtn.addEventListener("click", () => {
      renderStageSelect();
      showScreen("stageSelect");
    });
    box.appendChild(backBtn);
  }

  let briefStageId = null;

  function showHistoryBrief(stage) {
    briefStageId = stage.id;
    document.getElementById("history-brief-title").textContent = stage.name;
    document.getElementById("history-brief-text").textContent = stage.history;
    showScreen("historyBrief");
  }

  document.getElementById("history-start-btn").addEventListener("click", () => {
    if (briefStageId) startStage(briefStageId);
  });

  document.getElementById("history-back-btn").addEventListener("click", () => {
    renderStageSelect();
    showScreen("stageSelect");
  });

  document.getElementById("start-btn").addEventListener("click", () => {
    currentStagesForSelect = STAGES;
    document.getElementById("stage-select-title").textContent = "ステージ選択（中華編）";
    renderStageSelect();
    showScreen("stageSelect");
  });

  document.getElementById("history-btn").addEventListener("click", () => {
    currentStagesForSelect = HISTORY_STAGES;
    document.getElementById("stage-select-title").textContent = "ステージ選択（歴史編）";
    renderStageSelect();
    showScreen("stageSelect");
  });

  document.getElementById("title-back-btn").addEventListener("click", () => {
    showScreen("title");
  });

  // ---- 国盗り編（地図・交渉・制圧） ----

  let conquestState = null;

  function enterConquestScreen() {
    if (!conquestState) conquestState = createConquestState();
    showScreen("conquest");
    const root = document.getElementById("conquest-root");
    mountConquestUI(root, conquestState, {
      onAttack: (province) => startConquestBattle(province),
      onUnified: () => {
        conquestState = null;
        showScreen("title");
      },
    });
  }

  function startConquestBattle(province) {
    const stage = withRoster(generateProvinceBattleStage(province));
    const state = createBattleState(stage);
    const battleRoot = document.getElementById("battle-root");
    showScreen("battle");
    mountBattleUI(battleRoot, state, (outcome) => {
      resolveConquerResult(conquestState, province.id, outcome);
      enterConquestScreen();
    });
  }

  document.getElementById("conquest-btn").addEventListener("click", () => {
    enterConquestScreen();
  });

  // ---- 編成 ----

  document.getElementById("formation-btn").addEventListener("click", () => {
    showScreen("formation");
    mountFormationUI(document.getElementById("formation-root"));
  });

  document.getElementById("formation-back-btn").addEventListener("click", () => {
    showScreen("title");
  });

  showScreen("title");
})();
