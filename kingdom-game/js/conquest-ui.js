// 国盗り編の画面描画。地図（国のノード）・交渉/制圧パネル・ターン進行を扱う。

(function () {
  window.KG = window.KG || {};
  const {
    getActionableTargets,
    negotiateCost,
    negotiateSuccessChance,
    negotiate,
    endConquestTurn,
  } = window.KG.conquest;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function mountConquestUI(root, state, { onAttack, onUnified }) {
    let selectedId = null;
    let unifiedNotified = false;
    let mapExpanded = false;

    function render() {
      root.innerHTML = "";

      const bar = el("div", "status-bar");
      bar.appendChild(el("div", "status-item", `ターン ${state.turn}`));
      bar.appendChild(el("div", "status-item", `兵糧 ${state.hyourou}`));
      const ownedCount = state.provinces.filter((p) => p.owner === "player").length;
      bar.appendChild(el("div", "status-item", `自国 ${ownedCount} / ${state.provinces.length}`));
      const expandBtn = el("button", "action-btn map-expand-btn", mapExpanded ? "地図を縮小" : "地図を拡大");
      expandBtn.addEventListener("click", () => {
        mapExpanded = !mapExpanded;
        render();
      });
      bar.appendChild(expandBtn);
      root.appendChild(bar);

      const main = el("div", "conquest-main");

      const mapWrap = el("div", "conquest-map");
      if (mapExpanded) mapWrap.classList.add("expanded");
      const actionableIds = new Set(getActionableTargets(state).map((p) => p.id));

      for (const province of state.provinces) {
        const node = el("button", "province-node");
        node.style.left = `${province.x}%`;
        node.style.top = `${province.y}%`;
        node.classList.add(province.owner === "player" ? "province-player" : "province-rival");
        if (province.owner !== "player" && actionableIds.has(province.id)) {
          node.classList.add("province-actionable");
        }
        if (selectedId === province.id) node.classList.add("province-selected");
        node.appendChild(el("div", "province-name", province.name));
        if (province.owner !== "player") {
          node.appendChild(el("div", "province-strength", `勢${province.strength}`));
        }
        node.addEventListener("click", () => {
          selectedId = selectedId === province.id ? null : province.id;
          render();
        });
        mapWrap.appendChild(node);
      }
      main.appendChild(mapWrap);

      const side = el("div", "conquest-side");
      side.appendChild(buildActionPanel());
      side.appendChild(buildLog());
      main.appendChild(side);

      root.appendChild(main);

      const footer = el("div", "footer-bar");
      const endBtn = el("button", "end-turn-btn", "ターン終了");
      endBtn.addEventListener("click", () => {
        endConquestTurn(state);
        selectedId = null;
        render();
      });
      footer.appendChild(endBtn);
      root.appendChild(footer);

      if (state.unified) {
        const overlay = el("div", "end-overlay");
        const box = el("div", "end-box");
        box.appendChild(el("div", "end-title", "天下統一！"));
        const btn = el("button", "action-btn", "タイトルへ戻る");
        btn.addEventListener("click", () => {
          if (!unifiedNotified) {
            unifiedNotified = true;
            onUnified();
          }
        });
        box.appendChild(btn);
        overlay.appendChild(box);
        root.appendChild(overlay);
      }
    }

    function buildActionPanel() {
      const panel = el("div", "selected-panel");
      if (!selectedId) {
        panel.appendChild(el("div", "panel-title", "国を選択してください"));
        return panel;
      }
      const province = state.provinces.find((p) => p.id === selectedId);
      if (!province) return panel;

      panel.appendChild(el("div", "panel-title", province.name));

      if (province.owner === "player") {
        panel.appendChild(el("div", "unit-stats", "自国。安泰である。"));
        return panel;
      }

      panel.appendChild(el("div", "unit-stats", `勢力 ${province.strength}`));

      const actionable = getActionableTargets(state).some((p) => p.id === province.id);
      if (!actionable) {
        panel.appendChild(el("div", "hint-text", "自国と隣接していないため、まだ手を出せません"));
        return panel;
      }

      const cost = negotiateCost(province);
      const chance = Math.round(negotiateSuccessChance(province) * 100);
      panel.appendChild(el("div", "hint-text", `交渉: 兵糧${cost} ・ 成功率${chance}%`));

      const buttons = el("div", "action-buttons");

      const negotiateBtn = el("button", "action-btn", "交渉");
      if (state.hyourou < cost) negotiateBtn.disabled = true;
      negotiateBtn.addEventListener("click", () => {
        negotiate(state, province.id);
        render();
      });
      buttons.appendChild(negotiateBtn);

      const attackBtn = el("button", "action-btn skill-btn", "制圧");
      attackBtn.addEventListener("click", () => onAttack(province));
      buttons.appendChild(attackBtn);

      panel.appendChild(buttons);
      return panel;
    }

    function buildLog() {
      const log = el("div", "log-panel");
      log.appendChild(el("div", "panel-title", "情勢ログ"));
      const list = el("div", "log-list");
      for (const line of state.log.slice(-10)) {
        list.appendChild(el("div", "log-line", line));
      }
      log.appendChild(list);
      return log;
    }

    render();
  }

  window.KG.conquestUi = { mountConquestUI };
})();
