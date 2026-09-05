// 編成画面の描画。武将・城/砦を一覧表示し、持ち込むかどうかをトグルできる。
// 編成した内容は roster.js が localStorage に保存し、main.js が戦闘開始時に allowedUnits へ合流させる。

(function () {
  window.KG = window.KG || {};
  const { getAllPremiumUnits, isEquipped, toggleEquipped } = window.KG.roster;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function buildCard(unit, onToggle) {
    const card = el("div", "formation-card");
    if (isEquipped(unit.id)) card.classList.add("equipped");

    card.appendChild(el("div", "unit-icon", unit.icon));
    card.appendChild(el("div", "hand-name", unit.name));
    card.appendChild(el("div", "hand-cost", `コスト ${unit.cost}`));
    if (unit.skill) {
      card.appendChild(el("div", "hint-text", `${unit.skill.name}：${unit.skill.desc}`));
    } else {
      card.appendChild(el("div", "hint-text", `HP${unit.hp} 攻${unit.atk} 守${unit.defBonus}（動けない代わりに硬い）`));
    }

    const btn = el("button", "action-btn", isEquipped(unit.id) ? "編成済み ✓" : "編成する");
    btn.addEventListener("click", () => onToggle(unit.id));
    card.appendChild(btn);
    return card;
  }

  function mountFormationUI(root) {
    function render() {
      root.innerHTML = "";

      const intro = el(
        "div",
        "hint-text",
        "コストが非常に高い（すべて7）ので、序盤に出すと他のユニットをほとんど配置できなくなる。ここぞという場面で使おう。編成した武将・城は、以降すべての戦闘で配置できるようになる。"
      );
      root.appendChild(intro);

      const units = getAllPremiumUnits();

      const heroSection = el("div", "formation-section");
      heroSection.appendChild(el("div", "panel-title", "武将"));
      const heroGrid = el("div", "formation-grid");
      units
        .filter((u) => u.kind === "hero")
        .forEach((u) => heroGrid.appendChild(buildCard(u, handleToggle)));
      heroSection.appendChild(heroGrid);
      root.appendChild(heroSection);

      const castleSection = el("div", "formation-section");
      castleSection.appendChild(el("div", "panel-title", "城・砦"));
      const castleGrid = el("div", "formation-grid");
      units
        .filter((u) => u.kind === "castle")
        .forEach((u) => castleGrid.appendChild(buildCard(u, handleToggle)));
      castleSection.appendChild(castleGrid);
      root.appendChild(castleSection);
    }

    function handleToggle(id) {
      toggleEquipped(id);
      render();
    }

    render();
  }

  window.KG.formationUi = { mountFormationUI };
})();
