/* おぐそーのカードゲーム PoC — 画面ロジック
   サーバーから盤面(view)を受け取って描画するだけ。ルール判定は一切しない。
   「今できること」は view.actions に入って降ってくるので、それをUIに紐づける。 */

const $ = (id) => document.getElementById(id);
const RED_SUITS = new Set(["H", "D"]);

let STATE = null;
let REF = null;      // カード図鑑データ（一度取ったら使い回す）
let busy = false;

/* ------------------------------------------------------------ 通信 */
async function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, opt);
  return res.json();
}

async function refresh() {
  STATE = await api("/api/state");
  render();
}

async function send(action) {
  if (busy) return;
  busy = true;
  setBusy(true);
  try {
    STATE = await api("/api/action", { action });
    render();
  } finally {
    busy = false;
    setBusy(false);
  }
}

function setBusy(on) {
  document.body.style.cursor = on ? "progress" : "";
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

/* ------------------------------------------------------- カード描画 */
function monsterCard(m, opts) {
  opts = opts || {};
  if (!m) {
    const e = document.createElement("div");
    e.className = "slot-empty";
    e.textContent = "空き";
    return e;
  }
  const el = document.createElement("div");
  el.className = "card";
  if (RED_SUITS.has(m.suit)) el.classList.add("red");
  if (m.is_demon) el.classList.add("demon");
  if (m.fatigue > 0) el.classList.add("fatigued");
  if (opts.onClick) {
    el.classList.add("clickable");
    el.addEventListener("click", opts.onClick);
    el.title = opts.title || "";
  }

  const hpRate = Math.max(0, Math.min(1, m.hp / m.hp_max));
  const badges = [];
  if (m.fatigue > 0) badges.push('<span class="chip warn">😴 疲労' + m.fatigue + "</span>");
  if (m.poison > 0) badges.push('<span class="chip warn">☠️ 毒' + m.poison + "</span>");
  if (m.curse > 0) badges.push('<span class="chip warn">🩸 呪' + m.curse + "</span>");
  if (m.is_demon) badges.push('<span class="chip info">👹 あと' + m.demon_turns + "T</span>");
  if (m.revived) badges.push('<span class="chip good">🔥 復活済</span>');
  badges.push('<span class="chip info">残攻撃' + m.attacks_left + "</span>");
  (m.equipment || []).forEach((eq) => {
    badges.push('<span class="chip good">' + escapeHtml(eq) + "</span>");
  });

  el.innerHTML =
    '<div class="card-top"><span class="mark">' + m.mark + "</span>" +
      '<span class="rank">' + m.rank_label + "</span></div>" +
    '<div class="card-name">' + escapeHtml(m.name) + "</div>" +
    '<div class="stats"><span class="atk">⚔ ' + m.atk_now + "</span>" +
      '<span class="def">🛡 ' + m.def_now + "</span></div>" +
    '<div class="hpbar"><div class="hpfill ' + (opts.mine ? "mine" : "enemy") +
      '" style="width:' + hpRate * 100 + '%"></div></div>' +
    '<div class="hptext">' + m.hp + " / " + m.hp_max + "</div>" +
    '<div class="badges">' + badges.join("") + "</div>" +
    '<div class="ability">' + (m.ability ? escapeHtml(m.ability.text) : "") + "</div>" +
    zoomPop(monsterZoom(m), opts.mine);
  return el;
}

function monsterZoom(m) {
  let h = '<div class="zp-head"><span class="zp-mark">' + m.mark + m.rank_label + "</span>" +
            '<span class="zp-name">' + escapeHtml(m.name) + "</span></div>";
  h += '<div class="zp-stats">⚔ 攻撃 <b>' + m.atk_now + "</b>　🛡 防御 <b>" + m.def_now +
         "</b>　❤️ HP <b>" + m.hp + " / " + m.hp_max + "</b></div>";
  if (m.ability) {
    h += '<div class="zp-abname">✨ ' + escapeHtml(m.ability.name) + "</div>";
    h += '<div class="zp-abtext">' + escapeHtml(m.ability.text) + "</div>";
  } else {
    h += '<div class="zp-abtext zp-none">技なし</div>';
  }
  const st = [];
  if (m.fatigue > 0) st.push("😴 疲労中（あと" + m.fatigue + "ターン攻撃できない）");
  if (m.poison > 0) st.push("☠️ 毒（毎ターン" + m.poison + "ダメージ）");
  if (m.curse > 0) st.push("🩸 呪い（毎ターン" + m.curse + "ダメージ）");
  if (m.is_demon) st.push("👹 魔王（あと" + m.demon_turns + "ターンで消滅）");
  if (m.revived) st.push("🔥 不死鳥で復活済み（もう復活できない）");
  st.push("🚪 あと " + m.attacks_left + " 回攻撃したら退場");
  if ((m.equipment || []).length) st.push("🎒 装備: " + m.equipment.join(" / "));
  h += '<div class="zp-status">' + st.map(escapeHtml).join("<br>") + "</div>";
  return h;
}

function itemCard(c, usable, onClick) {
  const el = document.createElement("div");
  el.className = "item-card " + (usable ? "usable" : "disabled");
  if (RED_SUITS.has(c.suit)) el.classList.add("red");
  if (usable) el.addEventListener("click", onClick);
  const text = c.effect ? c.effect.text : "";
  el.innerHTML =
    '<div class="item-head"><span>' + c.mark + "</span><span>" + c.rank_label + "</span></div>" +
    '<div class="item-name">' + escapeHtml(c.name) + "</div>" +
    '<div class="item-text">' + escapeHtml(text) + "</div>" +
    zoomPop(itemZoom(c, usable), true);
  return el;
}

function itemZoom(c, usable) {
  let h = '<div class="zp-head"><span class="zp-mark">' + c.mark + c.rank_label + "</span>" +
            '<span class="zp-name">' + escapeHtml(c.name) + "</span></div>";
  h += '<div class="zp-abtext">' + escapeHtml(c.effect ? c.effect.text : "") + "</div>";
  h += '<div class="zp-status">' +
         (usable ? "🖱️ クリックで使えます" : "⛔ いまは使えません（対象がいない／使用済みなど）") +
       "</div>";
  return h;
}

function zoomPop(inner, mine) {
  return '<div class="zoom-pop ' + (mine ? "zp-up" : "zp-down") + '">' + inner + "</div>";
}

/* ------------------------------------------------------------ 描画 */
function render() {
  if (!STATE) return;
  const me = STATE.me, op = STATE.opponent;
  const acts = STATE.actions || [];
  const byType = {};
  acts.forEach((a) => { (byType[a.type] = byType[a.type] || []).push(a); });

  $("turnLabel").textContent = "ターン " + STATE.turn;
  const who = $("whoseTurn");
  who.textContent = STATE.is_my_turn ? "あなたの番" : "CPUの番";
  who.className = "badge " + (STATE.is_my_turn ? "mine" : "enemy");

  // --- トレーナー ---
  $("opName").textContent = op.name;
  $("opHpText").textContent = op.trainer_hp + " / " + op.trainer_hp_max;
  $("opHpFill").style.width = pct(op.trainer_hp, op.trainer_hp_max);
  $("opCounts").textContent =
    "🃏 山札 " + op.deck_count + "　🗑️ 捨札 " + op.discard_count + "　🎒 手札 " + op.hand_count + "枚";

  $("myName").textContent = me.name;
  $("myHpText").textContent = me.trainer_hp + " / " + me.trainer_hp_max;
  $("myHpFill").style.width = pct(me.trainer_hp, me.trainer_hp_max);
  $("myCounts").textContent =
    "🃏 山札 " + me.deck_count + "　🗑️ 捨札 " + me.discard_count +
    "　🎒 アイテム山 " + STATE.item_deck_count + "　" + optionSummary();

  // --- 場 ---
  fill($("opBattle"), [op.battle], { mine: false });
  fill($("opBench"), op.bench, { mine: false });
  fill($("myBattle"), [me.battle], { mine: true });

  const benchBox = $("myBench");
  benchBox.innerHTML = "";
  me.bench.forEach((m, i) => {
    const swap = (byType.swap || []).find((a) => a.bench === i);
    benchBox.appendChild(monsterCard(m, {
      mine: true,
      onClick: swap ? () => send({ type: "swap", bench: i }) : null,
      title: swap ? "クリックでバトル場と交代" : "",
    }));
  });

  // --- 手札 ---
  const handBox = $("myHand");
  handBox.innerHTML = "";
  if (!me.hand.length) {
    handBox.innerHTML = '<div class="acthint">手札なし</div>';
  }
  me.hand.forEach((c, i) => {
    const use = (byType.item || []).find((a) => a.hand === i);
    handBox.appendChild(itemCard(c, !!use, () => send({ type: "item", hand: i })));
  });

  // --- 操作ボタン ---
  const atk = (byType.attack || [])[0];
  $("attackBtn").disabled = !atk;
  $("attackBtn").textContent = atk ? atk.label : "⚔️ 攻撃";
  $("endTurnBtn").disabled = !(byType.end_turn || []).length;

  $("actHint").textContent = hintText(STATE, me, byType);

  // --- ログ ---
  const logBox = $("logList");
  logBox.innerHTML = "";
  (STATE.log || []).forEach((line, i, arr) => {
    const d = document.createElement("div");
    d.textContent = line;
    if (line.indexOf("────") === 0) d.className = "turnline";
    if (i === arr.length - 1) d.classList.add("newest");
    logBox.appendChild(d);
  });
  logBox.scrollTop = logBox.scrollHeight;

  // --- 決着 ---
  const ov = $("overlay");
  if (STATE.winner !== null && STATE.winner !== undefined) {
    const win = STATE.winner === STATE.viewer;
    $("ovTitle").textContent = STATE.winner === -1 ? "🤝" : (win ? "🏆" : "💀");
    $("ovText").textContent =
      (STATE.winner === -1 ? "引き分け" : (win ? "あなたの勝ち！" : "あなたの負け…")) +
      (STATE.finish_reason ? "（" + STATE.finish_reason + "）" : "");
    ov.classList.remove("hidden");
  } else {
    ov.classList.add("hidden");
  }
}

function optionSummary() {
  const o = (STATE && STATE.options) || {};
  const off = [];
  if (!o.monster_abilities) off.push("技なし");
  else if (!o.demon_lord) off.push("魔王なし");
  return off.length ? "⚙️ " + off.join("・") : "";
}

function hintText(st, me, byType) {
  if (st.winner !== null && st.winner !== undefined) return "ゲーム終了";
  if (!st.is_my_turn) return "CPUが考え中…";
  const bits = [];
  if (me.battle && me.battle.fatigue > 0) bits.push("バトル場は疲労中（攻撃できない）");
  if (me.item_used) bits.push("アイテムは使用済み");
  if (me.swaps_left <= 0) bits.push("交代は使用済み");
  if (!byType.attack && me.battle && me.battle.fatigue <= 0 && me.attacked) {
    bits.push("このターンはもう攻撃済み");
  }
  return bits.join(" / ") || "行動を選んでね";
}

function fill(box, list, opts) {
  box.innerHTML = "";
  list.forEach((m) => box.appendChild(monsterCard(m, opts)));
}

function pct(v, max) {
  return Math.max(0, Math.min(100, (v / max) * 100)) + "%";
}

/* ------------------------------------------------------ タブと図鑑 */
function initTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tabpanel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("panel-" + btn.dataset.tab).classList.add("active");
      if (btn.dataset.tab !== "log") loadReference();
    });
  });
}

async function loadReference() {
  if (REF) return;
  try {
    REF = await api("/api/reference");
    $("refItem").innerHTML = CardRef.itemHtml(REF, false);
    $("refMonster").innerHTML = CardRef.monsterHtml(REF, false);
  } catch (e) {
    $("refItem").innerHTML = '<div class="ref-note">読み込みに失敗しました: ' + e + "</div>";
  }
}

/* ------------------------------------------------------ オプション */
function openOptions() {
  const o = (STATE && STATE.options) || {};
  $("optAbilities").checked = !!o.monster_abilities;
  $("optDemon").checked = !!o.demon_lord;
  syncOptionLock();
  $("optionOverlay").classList.remove("hidden");
}

function syncOptionLock() {
  // 技がオフなら、魔王（♠Aの技）も使えない
  const on = $("optAbilities").checked;
  $("optDemon").disabled = !on;
  if (!on) $("optDemon").checked = false;
}

async function applyOptions() {
  const options = {
    monster_abilities: $("optAbilities").checked,
    demon_lord: $("optAbilities").checked && $("optDemon").checked,
  };
  $("optionOverlay").classList.add("hidden");
  STATE = await api("/api/new", { options: options });
  render();
}

/* ------------------------------------------------------------ 起動 */
$("attackBtn").addEventListener("click", () => send({ type: "attack" }));
$("endTurnBtn").addEventListener("click", () => send({ type: "end_turn" }));
$("newGameBtn").addEventListener("click", async () => {
  STATE = await api("/api/new", {});
  render();
});
$("ovBtn").addEventListener("click", async () => {
  STATE = await api("/api/new", {});
  render();
});
$("optionBtn").addEventListener("click", openOptions);
$("optCancel").addEventListener("click", () => $("optionOverlay").classList.add("hidden"));
$("optApply").addEventListener("click", applyOptions);
$("optAbilities").addEventListener("change", syncOptionLock);

initTabs();
refresh();
