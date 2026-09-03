/* おぐそーのカードゲーム — 画面ロジック

   サーバーから盤面(view)を受け取って描画するだけ。ルール判定は一切しない。
   「今できること」は view.actions に入って降ってくるので、それをUIに紐づける。

   CPU対戦もLAN対戦も「部屋(room)」として同じAPIで動く。
   違いは、LANのときだけ相手の操作を拾うためにポーリングすること。 */

const $ = (id) => document.getElementById(id);
const RED_SUITS = new Set(["H", "D"]);
const STORE_KEY = "cardgame.session";
const POLL_MS = 1200;

let SESSION = null;   // {code, token, seat, mode}
let STATE = null;     // サーバーから来た盤面
let REF = null;       // カード図鑑（一度取ったら使い回す）
let lastRev = -1;
let pollTimer = null;
let roomListTimer = null;
let busy = false;

/* タッチ端末（スマホ・タブレット）かどうか。
   スマホには「マウスを乗せる」が無いので、拡大表示をタップに切り替える。
   マウスのあるPCでは従来どおりホバーで出す。 */
const TOUCH = window.matchMedia && window.matchMedia("(hover: none)").matches;
if (TOUCH) document.body.classList.add("touch");

/* ============================================================== 通信 */
async function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, opt);
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    throw new Error((data && data.error) || ("通信に失敗しました (" + res.status + ")"));
  }
  return data;
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

function saveSession() {
  try {
    if (SESSION) localStorage.setItem(STORE_KEY, JSON.stringify(SESSION));
    else localStorage.removeItem(STORE_KEY);
  } catch (e) { /* プライベートウィンドウ等。使えなくても動く */ }
}

function loadSession() {
  try {
    const s = localStorage.getItem(STORE_KEY);
    return s ? JSON.parse(s) : null;
  } catch (e) { return null; }
}

/* ============================================================ ロビー */
function showLobby(screen) {
  stopPolling();
  document.body.classList.add("in-lobby");
  $("lobby").classList.remove("hidden");
  document.querySelectorAll(".lobbyscreen").forEach((s) => s.classList.remove("active"));
  $(screen).classList.add("active");
  hideErr();
  if (screen === "lb-join") startRoomList(); else stopRoomList();
  if (screen !== "lb-wait" && screen !== "lb-join") stopPolling();
}

function hideLobby() {
  document.body.classList.remove("in-lobby");
  $("lobby").classList.add("hidden");
  stopRoomList();
}

function showErr(msg) {
  const e = $("lobbyErr");
  e.textContent = "⚠️ " + msg;
  e.classList.remove("hidden");
}
function hideErr() { $("lobbyErr").classList.add("hidden"); }

function playerName() {
  const v = ($("playerName").value || "").trim();
  return v || "なまえなし";
}

async function createRoom(mode) {
  try {
    const r = await api("/api/room/create", { mode: mode, name: mode === "lan" ? playerName() : "あなた" });
    SESSION = { code: r.code, token: r.token, seat: r.seat, mode: mode };
    saveSession();
    if (mode === "cpu") {
      enterGame(r.state);
    } else {
      $("roomCode").textContent = r.code;
      showLobby("lb-wait");
      startPolling();     // 相手が来たら自動で始まる
    }
  } catch (e) { showErr(e.message); }
}

async function joinRoom(code) {
  try {
    const r = await api("/api/room/join", { code: code, name: playerName() });
    SESSION = { code: r.code, token: r.token, seat: r.seat, mode: "lan" };
    saveSession();
    enterGame(r.state);
  } catch (e) { showErr(e.message); }
}

function startRoomList() {
  stopRoomList();
  refreshRoomList();
  roomListTimer = setInterval(refreshRoomList, 2000);
}
function stopRoomList() {
  if (roomListTimer) { clearInterval(roomListTimer); roomListTimer = null; }
}

async function refreshRoomList() {
  let rooms = [];
  try {
    rooms = (await api("/api/room/list")).rooms || [];
  } catch (e) { return; }
  const box = $("roomList");
  if (!rooms.length) {
    box.innerHTML = '<div class="emptyroom">開いている部屋はありません。<br>' +
      "相手に「部屋を作る」をやってもらってね。</div>";
    return;
  }
  box.innerHTML = "";
  rooms.forEach((r) => {
    const b = document.createElement("button");
    b.className = "roomitem";
    b.innerHTML = '<span class="ri-code">' + escapeHtml(r.code) + "</span>" +
      '<span class="ri-host">' + escapeHtml(r.host) + " さんの部屋</span>" +
      '<span class="ri-wait">' + Math.floor(r.waiting_seconds / 60) + "分待機中</span>";
    b.addEventListener("click", () => joinRoom(r.code));
    box.appendChild(b);
  });
}

/* ============================================================ ゲーム */
function enterGame(view) {
  hideLobby();
  STATE = view;
  lastRev = -1;
  render();
  if (SESSION && SESSION.mode === "lan") startPolling();
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(poll, POLL_MS);
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function poll() {
  if (!SESSION || busy) return;
  let v;
  try {
    v = await api("/api/room/state?code=" + encodeURIComponent(SESSION.code) +
                  "&token=" + encodeURIComponent(SESSION.token));
  } catch (e) {
    return;   // 一時的な失敗は無視。次のポーリングで拾う
  }
  const wasWaiting = STATE && STATE.room && STATE.room.waiting;
  STATE = v;
  if (wasWaiting && !v.room.waiting) {
    enterGame(v);      // 相手が来た！
    return;
  }
  if (v.room.waiting) return;   // まだ待機中
  render();
}

async function send(action) {
  if (busy || !SESSION) return;
  busy = true;
  document.body.style.cursor = "progress";
  try {
    STATE = await api("/api/room/action",
      { code: SESSION.code, token: SESSION.token, action: action });
    render();
  } catch (e) {
    showToast(e.message);
  } finally {
    busy = false;
    document.body.style.cursor = "";
  }
}

async function rematch(options) {
  if (!SESSION) return;
  try {
    const body = { code: SESSION.code, token: SESSION.token };
    if (options) body.options = options;
    STATE = await api("/api/room/rematch", body);
    lastRev = -1;
    render();
  } catch (e) { showToast(e.message); }
}

function leaveRoom() {
  stopPolling();
  SESSION = null;
  STATE = null;
  saveSession();
  showLobby("lb-mode");
}

function showToast(msg) {
  const b = $("pauseBanner");
  b.textContent = "⚠️ " + msg;
  b.classList.remove("hidden");
  setTimeout(() => b.classList.add("hidden"), 3000);
}

/* ======================================================= カード描画 */
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
    el.title = opts.title || "";
  }
  if (TOUCH) {
    // スマホは「タップで詳細を開く → ボタンで実行」の2段階にする。
    // 指が当たっただけで交代してしまう事故を防げるので、そのほうが安全。
    el.addEventListener("click", () => openSheet(monsterZoom(m), opts.onClick, opts.actionLabel));
  } else if (opts.onClick) {
    el.addEventListener("click", opts.onClick);
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
  if (TOUCH) {
    el.addEventListener("click", () => openSheet(
      itemZoom(c, usable), usable ? onClick : null, "🎒 このカードを使う"));
  } else if (usable) {
    el.addEventListener("click", onClick);
  }
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

/* ------------------------------------------ カード詳細シート（スマホ） */
let sheetAction = null;

function openSheet(html, action, label) {
  $("sheetBody").innerHTML = html;
  const btn = $("sheetAction");
  sheetAction = action || null;
  if (sheetAction) {
    btn.textContent = label || "これを選ぶ";
    btn.classList.remove("hidden");
  } else {
    btn.classList.add("hidden");
  }
  $("cardSheet").classList.remove("hidden");
}

function closeSheet() {
  $("cardSheet").classList.add("hidden");
  sheetAction = null;
}

/* ============================================================== 描画 */
function render() {
  if (!STATE || !STATE.me) return;
  const me = STATE.me, op = STATE.opponent;
  const acts = STATE.actions || [];
  const byType = {};
  acts.forEach((a) => { (byType[a.type] = byType[a.type] || []).push(a); });

  // 相手の操作でしか変わらない場面では、無駄な再描画をしない
  const rev = STATE.rev;
  const sameRev = (rev !== undefined && rev === lastRev);
  lastRev = rev;

  $("turnLabel").textContent = "ターン " + STATE.turn;
  const who = $("whoseTurn");
  who.textContent = STATE.is_my_turn ? "あなたの番" : (op.name + " の番");
  who.className = "badge " + (STATE.is_my_turn ? "mine" : "enemy");

  // 部屋の表示
  const room = STATE.room || {};
  const tag = $("roomTag");
  if (room.mode === "lan") {
    tag.textContent = "🌐 LAN " + room.code;
    tag.classList.remove("hidden");
  } else {
    tag.textContent = "🤖 CPU対戦";
    tag.classList.remove("hidden");
  }

  // 相手の接続状態
  const banner = $("pauseBanner");
  if (room.mode === "lan" && !room.opponent_online) {
    banner.textContent = "📡 " + (op.name || "相手") + " の接続が切れているみたい…（画面を開き直すと戻ります）";
    banner.classList.remove("hidden");
  } else if (banner.textContent.indexOf("📡") === 0) {
    banner.classList.add("hidden");
  }

  if (sameRev) return;   // 中身が変わっていないので以降は描き直さない

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
      actionLabel: "🔄 バトル場と交代する",
      title: swap ? "クリックでバトル場と交代" : "",
    }));
  });

  // --- 手札 ---
  const handBox = $("myHand");
  handBox.innerHTML = "";
  if (!me.hand.length) handBox.innerHTML = '<div class="acthint">手札なし</div>';
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
  if (!st.is_my_turn) {
    return st.room && st.room.mode === "lan"
      ? "相手の番です。待ってね…" : "CPUが考え中…";
  }
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

/* ======================================================= タブと図鑑 */
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
    $("refItem").innerHTML = '<div class="ref-note">読み込みに失敗しました: ' + e.message + "</div>";
  }
}

/* ======================================================= オプション */
function openOptions() {
  const o = (STATE && STATE.options) || {};
  $("optAbilities").checked = !!o.monster_abilities;
  $("optDemon").checked = !!o.demon_lord;
  syncOptionLock();
  $("optionOverlay").classList.remove("hidden");
}

function syncOptionLock() {
  const on = $("optAbilities").checked;
  $("optDemon").disabled = !on;
  if (!on) $("optDemon").checked = false;
}

async function applyOptions() {
  $("optionOverlay").classList.add("hidden");
  await rematch({
    monster_abilities: $("optAbilities").checked,
    demon_lord: $("optAbilities").checked && $("optDemon").checked,
  });
}

/* ============================================================== 起動 */
$("attackBtn").addEventListener("click", () => send({ type: "attack" }));
$("endTurnBtn").addEventListener("click", () => send({ type: "end_turn" }));
$("newGameBtn").addEventListener("click", () => rematch(null));
$("ovBtn").addEventListener("click", () => rematch(null));
$("leaveBtn").addEventListener("click", leaveRoom);
$("optionBtn").addEventListener("click", openOptions);
$("optCancel").addEventListener("click", () => $("optionOverlay").classList.add("hidden"));
$("optApply").addEventListener("click", applyOptions);
$("optAbilities").addEventListener("change", syncOptionLock);
$("sheetClose").addEventListener("click", closeSheet);
$("sheetAction").addEventListener("click", () => {
  const a = sheetAction;
  closeSheet();
  if (a) a();
});
$("cardSheet").addEventListener("click", (e) => {
  if (e.target === $("cardSheet")) closeSheet();   // 外側をタップで閉じる
});

$("btnCpu").addEventListener("click", () => createRoom("cpu"));
$("btnLan").addEventListener("click", () => {
  const saved = localStorage.getItem("cardgame.name");
  if (saved) $("playerName").value = saved;
  showLobby("lb-lan");
});
$("btnMakeRoom").addEventListener("click", () => {
  localStorage.setItem("cardgame.name", playerName());
  createRoom("lan");
});
$("btnFindRoom").addEventListener("click", () => {
  localStorage.setItem("cardgame.name", playerName());
  showLobby("lb-join");
});
$("btnJoinCode").addEventListener("click", () => {
  const c = ($("joinCode").value || "").trim().toUpperCase();
  if (c.length !== 4) { showErr("合言葉は4文字だよ。"); return; }
  joinRoom(c);
});
$("joinCode").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("btnJoinCode").click();
});
document.querySelectorAll("[data-back]").forEach((b) => {
  b.addEventListener("click", () => {
    if (SESSION && SESSION.mode === "lan") { SESSION = null; saveSession(); stopPolling(); }
    showLobby(b.dataset.back);
  });
});

initTabs();

/* 前回の続きがあれば復帰する（F5しても席を失わないように） */
(async function boot() {
  const s = loadSession();
  if (!s) { showLobby("lb-mode"); return; }
  SESSION = s;
  try {
    const v = await api("/api/room/state?code=" + encodeURIComponent(s.code) +
                        "&token=" + encodeURIComponent(s.token));
    if (v.room && v.room.waiting) {
      $("roomCode").textContent = s.code;
      showLobby("lb-wait");
      startPolling();
    } else {
      enterGame(v);
    }
  } catch (e) {
    SESSION = null;
    saveSession();
    showLobby("lb-mode");
  }
})();
