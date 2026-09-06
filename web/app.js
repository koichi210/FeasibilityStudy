/* アルカナエクスプロージョン — 画面ロジック

   サーバーから盤面(view)を受け取って描画するだけ。ルール判定は一切しない。
   「今できること」は view.actions に入って降ってくるので、それをUIに紐づける。

   CPU対戦もLAN対戦も「部屋(room)」として同じAPIで動く。
   違いは、LANのときだけ相手の操作を拾うためにポーリングすること。 */

const $ = (id) => document.getElementById(id);
const RED_SUITS = new Set(["H", "D"]);
const STORE_KEY = "arcana.session";
const NAME_KEY = "arcana.name";
const POLL_MS = 1200;

/* 保存キーの引っ越し（cardgame.* → arcana.*）。
   フォルダ名を ArcanaExplosion にしたのに合わせて改名した。
   すでに遊んでいた人の名前と、中断中の対戦をそのまま引き継ぐ。
   みんなの移行が済んだら、このブロックは消してよい。 */
[[STORE_KEY, "cardgame.session"], [NAME_KEY, "cardgame.name"]].forEach(([now, old]) => {
  const v = localStorage.getItem(old);
  if (v !== null && localStorage.getItem(now) === null) localStorage.setItem(now, v);
  localStorage.removeItem(old);
});

let SESSION = null;   // {code, token, seat, mode}
let RESUMABLE = null; // 「モード選択へ」で中断した対戦。あとから戻れるように保持する
let STATE = null;     // サーバーから来た盤面
let REF = null;       // カード図鑑（一度取ったら使い回す）
let selectedEnemyHand = null;  // 選択中のエネミー手札のindex（null=未選択）
let prevHp = {};      // uid -> 直前に描画したHP（ダメージ/回復の点滅判定用）
let prevTrainerHp = { me: null, op: null };  // トレーナーHPの点滅判定用
let lastRev = -1;
let lostCount = 0;    // 「部屋が見つからない」が何回続いたか
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
    const err = new Error((data && data.error) || ("通信に失敗しました (" + res.status + ")"));
    err.status = res.status;
    throw err;
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
  updateResumeUi();
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

async function createRoom(mode, cpuLevel) {
  try {
    const body = { mode: mode, name: mode === "lan" ? playerName() : "あなた" };
    if (mode === "cpu" && cpuLevel) body.cpu_level = cpuLevel;
    const r = await api("/api/room/create", body);
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
  RESUMABLE = null;   // 新しい対戦に入ったので、中断していたものはもう戻れない
  STATE = view;
  selectedEnemyHand = null;
  prevHp = {};
  prevTrainerHp = { me: null, op: null };
  lastRev = -1;
  render();
  if (SESSION && SESSION.mode === "lan") startPolling();
  pumpCpu();   // CPUが先に動く場面なら、そのまま1手ずつ見せていく
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
    lostCount = 0;
  } catch (e) {
    // 一時的な通信エラーは無視して次のポーリングで拾う。
    // ただし「部屋が無い」(404)が続く場合は本当に消えているので、
    // 黙って固まらずに知らせる（席を外している間にサーバーが再起動した等）
    if (e.status === 404) {
      lostCount += 1;
      if (lostCount >= 4) {
        stopPolling();
        SESSION = null;
        saveSession();
        showToast("部屋が見つかりませんでした。サーバーが再起動したかもしれません。");
        showLobby("lb-mode");
      }
    }
    return;
  }
  const wasWaiting = STATE && STATE.room && STATE.room.waiting;
  STATE = v;
  if (wasWaiting && !v.room.waiting) {
    enterGame(v);      // 相手が来た！
    return;
  }
  if (v.room.waiting) return;   // まだ待機中
  await renderAfterFx();
}

async function send(action) {
  if (busy || !SESSION) return;
  selectedEnemyHand = null;
  busy = true;
  document.body.style.cursor = "progress";
  try {
    STATE = await api("/api/room/action",
      { code: SESSION.code, token: SESSION.token, action: action });
    // 前の攻撃の余韻が消えるまで待ってから次の盤面を出す。
    // 待たないと殴り合いが重なって、どちらが何をしたのか分からなくなる。
    await renderAfterFx();
  } catch (e) {
    showToast(e.message);
  } finally {
    busy = false;
    document.body.style.cursor = "";
  }
  pumpCpu();
}

/* CPUの手を1つずつ取りに行く。
   まとめて進めてもらうと、画面に届くのは全部終わった後の盤面だけになり、
   攻撃モーションを出したい相手のカードが既にベンチへ下がっていて出せない。
   1手ぶん進めては演出を見せ、終わったらまた次の1手…と繰り返す。 */
let cpuPumping = false;

async function pumpCpu() {
  if (cpuPumping) return;
  cpuPumping = true;
  try {
    let guard = 0;
    while (STATE && STATE.room && STATE.room.cpu_thinking && guard < 80) {
      guard += 1;
      await send({ type: "cpu_step" });   // send の中で演出の再生を待つ
    }
  } finally {
    cpuPumping = false;
  }
}

async function rematch(options, cpuLevel) {
  if (!SESSION) return;
  try {
    const body = { code: SESSION.code, token: SESSION.token };
    if (options) body.options = options;
    if (cpuLevel) body.cpu_level = cpuLevel;
    STATE = await api("/api/room/rematch", body);
    lastRev = -1;
    render();
  } catch (e) { showToast(e.message); }
}

/* モード選択へ戻る。
   ⚠️ ここで対戦を捨ててはいけない。
   うっかり押しただけで試合が消えるのは最悪なので、
   セッションは残したまま「中断」扱いにして、あとから戻れるようにする。
   実際に捨てるのは、新しい対戦を始めたとき（enterGame）だけ。 */
function leaveRoom() {
  stopPolling();
  if (SESSION) RESUMABLE = SESSION;
  showLobby("lb-mode");
}

function updateResumeUi() {
  const on = !!RESUMABLE;
  $("btnResume").classList.toggle("hidden", !on);
  $("resumeNote").classList.toggle("hidden", !on);
}

async function resumeGame() {
  if (!RESUMABLE) return;
  const s = RESUMABLE;
  try {
    const v = await api("/api/room/state?code=" + encodeURIComponent(s.code) +
                        "&token=" + encodeURIComponent(s.token));
    SESSION = s;
    saveSession();
    enterGame(v);
  } catch (e) {
    // 部屋が消えていた（サーバー再起動など）
    RESUMABLE = null;
    updateResumeUi();
    showErr("中断していた対戦は、もう続きから遊べませんでした。新しく始めてね。");
  }
}

function showToast(msg) {
  const b = $("pauseBanner");
  b.textContent = "⚠️ " + msg;
  b.classList.remove("hidden");
  setTimeout(() => b.classList.add("hidden"), 3000);
}

/* ======================================================= カード描画 */
// ベンチの支援カードによる一時バフは atk_now / def_now に含まれていないので、
// 「30(+30)」のように増分を添えて、いま実際にいくつなのかを分かるようにする。
function statWithBuff(v, buff) {
  if (!buff) return String(v);
  return v + '<span class="buffdelta">(+' + buff + ")</span>";
}

function enemyCard(m, opts) {
  opts = opts || {};
  if (!m) {
    // 配置先は手札クリック時に自動で決まるので、空き枠は押せない
    const e = document.createElement("div");
    e.className = "slot-empty";
    e.textContent = "空き";
    return e;
  }
  if (m.hidden) {
    // 相手のベンチ：いる事は分かるが中身（名前・技・HP）は伏せ札。
    const e = document.createElement("div");
    e.className = "card hidden-card";
    // 中身が分からないので、場所そのものを目印にして動きを追う
    if (opts.trackKey) e.dataset.cardkey = opts.trackKey;
    e.title = "相手のデッキ（中身は非公開）";
    e.innerHTML =
      '<div class="card-top"><span class="mark">🂠</span><span class="rank">？</span></div>' +
      '<div class="card-name">？？？</div>' +
      '<div class="stats"><span class="atk">⚔ ？</span><span class="def">🛡 ？</span></div>' +
      '<div class="hpbar"><div class="hpfill enemy" style="width:100%"></div></div>' +
      '<div class="hptext">？ / ？</div>' +
      '<div class="ability">🙈 伏せられています</div>';
    return e;
  }
  const el = document.createElement("div");
  el.className = "card";
  // uid はエネミーが場にいる間ずっと変わらないので、
  // 「ベンチ→バトル場」のように枠をまたいでも同じカードだと追跡できる。
  el.dataset.cardkey = "m" + m.uid;
  el.dataset.cardcode = m.code || "";
  if (RED_SUITS.has(m.suit)) el.classList.add("red");
  if (m.is_demon) el.classList.add("demon");
  if (m.fatigue > 0) el.classList.add("fatigued");
  if (opts.done) el.classList.add("done");
  if (opts.pick) el.classList.add("pick");   // 今まさに選んでもらいたいカード

  // 被弾の演出（点滅・爪痕）は、このカードが移動しているなら
  // 動き終わってから出す。動きながら斬られると何が起きたか分からないため。
  // ここでは「あとで付けるクラス」として控えておくだけ。
  const fxLater = [];
  if (opts.flash) fxLater.push(opts.flash);
  if (fxIsNew() && STATE.fx) {
    // 攻撃する側は移動しないので、揺れだけはその場で始めてよい
    if (STATE.fx.attacker === m.uid) el.classList.add("attacking");
    if (STATE.fx.target === m.uid) fxLater.push("clawed");
  }
  if (fxLater.length) el.dataset.fxafter = fxLater.join(" ");
  if (opts.onClick) {
    el.classList.add("clickable");
    el.title = opts.title || "";
  }
  // タップ・クリックはそのまま実行する（スマホでも確認は挟まない）。
  // 操作できないカードだけ、スマホではタップで詳細を見られるようにしておく
  // （PCはマウスを乗せれば見られるが、スマホにはその手段が無いため）。
  if (opts.onClick) {
    el.addEventListener("click", opts.onClick);
  } else if (TOUCH) {
    el.addEventListener("click", () => openSheet(enemyZoom(m), null, ""));
  }

  const hpRate = Math.max(0, Math.min(1, m.hp / m.hp_max));
  const badges = [];
  if (m.fatigue > 0) badges.push('<span class="chip warn">😴 疲労' + m.fatigue + "</span>");
  if (m.poison > 0) badges.push('<span class="chip warn">☠️ 毒' + m.poison + "</span>");
  if (m.curse > 0) badges.push('<span class="chip warn">🩸 呪' + m.curse + "</span>");
  if (m.is_demon) badges.push('<span class="chip info">👹 あと' + m.demon_turns + "T</span>");
  if (m.bench_turns_left != null) {
    badges.push('<span class="chip warn">⌛ デッキあと' + m.bench_turns_left + "T</span>");
  }
  if (m.revived) badges.push('<span class="chip good">🔥 復活済</span>');
  badges.push('<span class="chip info">残攻撃' + m.attacks_left + "</span>");
  (m.equipment || []).forEach((eq) => {
    badges.push('<span class="chip good">' + escapeHtml(eq) + "</span>");
  });

  el.innerHTML =
    '<div class="card-top"><span class="mark">' + m.mark + "</span>" +
      '<span class="rank">' + m.rank_label + "</span></div>" +
    '<div class="card-name">' + escapeHtml(m.name) + "</div>" +
    '<div class="stats"><span class="atk">⚔ ' + statWithBuff(m.atk_now, m.atk_buff) + "</span>" +
      '<span class="def">🛡 ' + statWithBuff(m.def_now, m.def_buff) + "</span></div>" +
    '<div class="hpbar"><div class="hpfill ' + (opts.mine ? "mine" : "enemy") +
      '" style="width:' + hpRate * 100 + '%"></div></div>' +
    '<div class="hptext">' + m.hp + " / " + m.hp_max + "</div>" +
    '<div class="badges">' + badges.join("") + "</div>" +
    '<div class="ability">' + (m.ability ? escapeHtml(m.ability.text) : "") + "</div>" +
    // 被弾の爪痕の器。実際に走るのは clawed クラスが付いた瞬間なので、
    // 置いておくだけならまだ何も見えない（移動が終わってから付ける）
    (fxLater.indexOf("clawed") >= 0 ? '<div class="claw"></div>' : "");
  attachHover(el, enemyZoom(m));
  return el;
}

function enemyZoom(m) {
  let h = '<div class="zp-head"><span class="zp-mark">' + m.mark + m.rank_label + "</span>" +
            '<span class="zp-name">' + escapeHtml(m.name) + "</span></div>";
  h += '<div class="zp-stats">⚔ 攻撃 <b>' + statWithBuff(m.atk_now, m.atk_buff) +
         "</b>　🛡 防御 <b>" + statWithBuff(m.def_now, m.def_buff) +
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
  if (m.atk_buff) st.push("👑 指揮官キングの支援：攻撃+" + m.atk_buff);
  if (m.def_buff) st.push("🛡️ 聖女クイーンの支援：防御+" + m.def_buff);
  if (m.is_demon) st.push("👹 魔王（あと" + m.demon_turns + "ターンで消滅）");
  if (m.bench_turns_left != null) {
    st.push("⌛ デッキにいられるのはあと" + m.bench_turns_left + "ターン（切れると強制退場）");
  }
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
  // 使えるカードはタップで即使用。使えないカードはスマホなら詳細だけ開く
  if (usable) {
    el.addEventListener("click", onClick);
  } else if (TOUCH) {
    el.addEventListener("click", () => openSheet(itemZoom(c, usable), null, ""));
  }
  const text = c.effect ? c.effect.text : "";
  el.innerHTML =
    '<div class="item-head"><span>' + c.mark + "</span><span>" + c.rank_label + "</span></div>" +
    '<div class="item-name">' + escapeHtml(c.name) + "</div>" +
    '<div class="item-text">' + escapeHtml(text) + "</div>";
  attachHover(el, itemZoom(c, usable));
  return el;
}

/* --------------------------------------- エネミー手札（配置前）の描画 */
function enemyHandCard(c, i, selected, placeable) {
  const el = document.createElement("div");
  el.className = "mh-card" + (RED_SUITS.has(c.suit) ? " red" : "") +
    (selected ? " selected" : "") + (placeable ? " placeable" : "");
  // 手札のカードには uid がまだ無いので、コード（♦Q など）で場のカードと結びつける。
  // これで「手札 → ベンチ」の移動も動いて見せられる。
  el.dataset.cardkey = "h" + c.code + "#" + i;
  el.dataset.cardcode = c.code;
  el.innerHTML =
    '<div class="mh-head"><span>' + c.mark + "</span><span>" + c.rank_label + "</span></div>" +
    '<div class="mh-name">' + escapeHtml(c.name) + "</div>" +
    '<div class="mh-stats"><span class="atk">⚔ ' + c.atk + "</span><span class=\"def\">🛡 " + c.dfn + "</span></div>" +
    '<div class="mh-ability">' + (c.ability ? escapeHtml(c.ability.text) : "") + "</div>";
  if (placeable) {
    el.title = "クリックで場に出す（バトル場が空ならそこへ、あとはデッキに左から詰めて置く）";
    el.addEventListener("click", () => placeAuto(i));
  } else if (TOUCH) {
    el.addEventListener("click", () => openSheet(enemyHandZoom(c), null, ""));
  }
  attachHover(el, enemyHandZoom(c));
  return el;
}

function enemyHandZoom(c) {
  let h = '<div class="zp-head"><span class="zp-mark">' + c.mark + c.rank_label + "</span>" +
            '<span class="zp-name">' + escapeHtml(c.name) + "</span></div>";
  h += '<div class="zp-stats">⚔ 攻撃 <b>' + c.atk + "</b>　🛡 防御 <b>" + c.dfn + "</b></div>";
  if (c.ability) {
    h += '<div class="zp-abname">✨ ' + escapeHtml(c.ability.name) + "</div>";
    h += '<div class="zp-abtext">' + escapeHtml(c.ability.text) + "</div>";
  } else {
    h += '<div class="zp-abtext zp-none">技なし</div>';
  }
  h += '<div class="zp-status">🃏 まだ場に出ていません。クリックするとそのまま場に出ます</div>';
  return h;
}

/* 置き場所は選ばせず、クリックだけで場に出す。
   バトル場が空ならそこを最優先（空のままだと直接攻撃されるため）、
   埋まっていればベンチの左から順に詰めていく。 */
function placeAuto(hand) {
  const spots = (STATE.actions || []).filter((a) => a.type === "place" && a.hand === hand);
  if (!spots.length) return;
  const battle = spots.find((a) => a.slot === "battle");
  const target = battle || spots
    .filter((a) => typeof a.slot === "number")
    .sort((a, b) => a.slot - b.slot)[0];
  if (target) send({ type: "place", hand: hand, slot: target.slot });
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

/* ----------------------------------- マウスホバーの拡大表示（PC用）
   吹き出しをカードの中に置くと、
     ・となりのカードが上に重なって隠れる
     ・画面の端で見切れる
   という問題が起きる。
   そこで画面直下に1つだけ置き、位置をJSで計算して画面内に収める。 */
function attachHover(el, html) {
  if (TOUCH) return;
  el.addEventListener("mouseenter", () => showHoverPop(el, html));
  el.addEventListener("mouseleave", hideHoverPop);
}

function showHoverPop(el, html) {
  const pop = $("hoverPop");
  pop.innerHTML = html;
  pop.classList.remove("hidden");

  const r = el.getBoundingClientRect();
  const pw = pop.offsetWidth;
  const ph = pop.offsetHeight;
  const m = 10;   // 画面ふちからの余白

  // 横：カードの中央に寄せつつ、画面からはみ出さないところまで戻す
  let left = r.left + r.width / 2 - pw / 2;
  left = Math.max(m, Math.min(left, window.innerWidth - pw - m));

  // 縦：まず上に出す。入らなければ下に出す。それも無理なら画面内に収める
  let top = r.top - ph - m;
  if (top < m) top = r.bottom + m;
  if (top + ph > window.innerHeight - m) {
    top = Math.max(m, window.innerHeight - ph - m);
  }

  pop.style.left = left + "px";
  pop.style.top = top + "px";
}

function hideHoverPop() {
  $("hoverPop").classList.add("hidden");
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
    tag.textContent = "🤖 CPU対戦" + (room.cpu_level_label ? "・" + room.cpu_level_label : "");
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

  // カードを作り直すので、出しっぱなしの吹き出しは消しておく
  hideHoverPop();

  // 描き直す前に、いまカードがどこにあったかを控えておく。
  // 描き直したあとの位置と見比べて「動いた／出た／消えた」を演出する。
  const cardsBefore = snapshotCards();

  // この描き直しで攻撃モーションを再生してよいかを決める（1回の攻撃につき1回だけ）
  beginFxFrame();

  // --- トレーナー ---
  $("opName").textContent = op.name;
  $("opHpText").textContent = op.trainer_hp + " / " + op.trainer_hp_max;
  $("opHpFill").style.width = pct(op.trainer_hp, op.trainer_hp_max);
  $("opCounts").textContent =
    "🃏 山札 " + op.deck_count + "　🗑️ 捨札 " + op.discard_count + "　🎒 手札 " + op.hand_count + "枚" +
    (op.enemy_hand_count ? "　🐣 配置前 " + op.enemy_hand_count + "体" : "");

  $("myName").textContent = me.name;
  $("myHpText").textContent = me.trainer_hp + " / " + me.trainer_hp_max;
  $("myHpFill").style.width = pct(me.trainer_hp, me.trainer_hp_max);
  $("myCounts").textContent =
    "🃏 山札 " + me.deck_count + "　🗑️ 捨札 " + me.discard_count +
    "　🎒 アイテム山 " + STATE.item_deck_count + "　" + optionSummary();

  // トレーナーHPが増減したら、枠ごとパッと色づかせる
  const opTrHp = prevTrainerHp.op;
  pulse($("opTrainer"), opTrHp == null ? null : (op.trainer_hp < opTrHp ? "hit" : op.trainer_hp > opTrHp ? "heal" : null));
  prevTrainerHp.op = op.trainer_hp;
  const myTrHp = prevTrainerHp.me;
  pulse($("myTrainer"), myTrHp == null ? null : (me.trainer_hp < myTrHp ? "hit" : me.trainer_hp > myTrHp ? "heal" : null));
  prevTrainerHp.me = me.trainer_hp;

  // --- 場 ---
  fill($("opBattle"), [op.battle], { mine: false });
  // 相手ベンチは伏せ札で中身が分からないので、枠の位置を目印に動きを追う
  fill($("opBench"), op.bench, { mine: false, trackPrefix: "opbench" });

  // 薄暗さは「その枠でできる事を使い切ったか」で決める。枠ごとに別々に見る。
  //   バトル場 … 攻撃を使ったら暗くする
  //   ベンチ   … 交代を使ったら暗くする
  // まとめて暗くすると、交代した直後のバトル場（まだ攻撃できる）まで
  // 暗くなってしまい、攻撃できないと勘違いさせてしまう。
  const battleSpent = !!me.attacked;
  const benchSpent = me.swaps_left <= 0;

  // 配置は手札をクリックした時点で自動的に決まるので、空き枠は押せない飾り。
  // 攻撃はバトル場のカードを直接クリックする（専用ボタンは廃止した）
  const atk = (byType.attack || [])[0];
  const battleBox = $("myBattle");
  battleBox.innerHTML = "";
  battleBox.appendChild(enemyCard(me.battle, {
    mine: true,
    flash: flashClass(me.battle),
    done: battleSpent,
    onClick: atk ? () => send({ type: "attack" }) : null,
    actionLabel: "⚔️ 攻撃する",
    title: atk ? atk.label + "（クリックで攻撃）" : attackBlockedLabel(STATE, me),
  }));

  // バトル場が空いて繰り上げを選ぶ番のときは、交代より優先してこちらを出す
  const mustPromote = STATE.pending_promote === STATE.viewer;
  const benchBox = $("myBench");
  benchBox.innerHTML = "";
  me.bench.forEach((m, i) => {
    const promote = (byType.promote || []).find((a) => a.bench === i);
    const swap = (byType.swap || []).find((a) => a.bench === i);
    benchBox.appendChild(enemyCard(m, {
      mine: true,
      flash: flashClass(m),
      // 選ばせている最中は、押せるカードを暗くしない
      done: benchSpent && !mustPromote,
      pick: !!promote,
      onClick: promote ? () => send({ type: "promote", bench: i })
               : swap ? () => send({ type: "swap", bench: i }) : null,
      actionLabel: promote ? "🔀 バトル場に出す" : "🔄 バトル場と交代する",
      title: promote ? "クリックでバトル場へ出す"
             : swap ? "クリックでバトル場と交代" : "",
    }));
  });

  // --- エネミー手札（配置前） ---
  // ※ サーバーを再起動しないまま画面だけ新しくなっていると enemy_hand が
  //   来ないことがある（起動しなおせば直る）ので、念のため空配列で受ける。
  const enemyHand = me.enemy_hand || [];
  const mhBox = $("myEnemyHand");
  mhBox.innerHTML = "";
  if (!enemyHand.length) mhBox.innerHTML = '<div class="acthint">手札なし</div>';
  enemyHand.forEach((c, i) => {
    const canPlace = (byType.place || []).some((a) => a.hand === i);
    mhBox.appendChild(enemyHandCard(c, i, false, canPlace));
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
  const canEnd = !!(byType.end_turn || []).length;
  const endBtn = $("endTurnBtn");
  endBtn.disabled = !canEnd;

  // ターン終了ボタンは信号機のように色で状況を伝える。
  //   🔴 赤   … 攻撃を残している。押すのはもったいない
  //   🟢 緑   … 攻撃は済んだ。まだ他にできる事はある
  //   🟡 金色 … もう何もできない。押してほしい（脈打たせる）
  // 常に光らせると見慣れて効かなくなるので、意味のあるときだけ色を付ける。
  const canDoSomething = !!(atk || (byType.place || []).length ||
                            (byType.item || []).length || (byType.swap || []).length);
  const chance = STATE.attack_chance;      // "now" / "after_swap" / null
  const hintEl = $("actHint");
  endBtn.classList.remove("nudge", "urge", "warn");
  hintEl.classList.remove("urge");

  let endLabel = "⏭️ ターン終了";
  if (canEnd && STATE.is_my_turn) {
    if (chance) {
      endBtn.classList.add("warn");
      endLabel = chance === "after_swap"
        ? "⏭️ ターン終了（交代すればまだ攻撃できます）"
        : "⏭️ ターン終了（まだ攻撃していません）";
    } else if (!canDoSomething) {
      endBtn.classList.add("urge");
      endLabel = "⏭️ ターン終了（もうできる事はありません）";
      hintEl.classList.add("urge");
    } else if (me.attacked) {
      endBtn.classList.add("nudge");
    }
  }
  endBtn.textContent = endLabel;
  hintEl.textContent = hintText(STATE, me, byType);

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

  // いま何を待っているのかを、ログの最後にそっと添える。
  // これは「起きた出来事」ではなく「今の状態」なので、履歴には残さず
  // 描き直すたびに付け替える。止まって見えるときの不安をなくすのが目的。
  const waitMsg = waitingText(STATE, op);
  if (waitMsg) {
    const w = document.createElement("div");
    w.className = "logwait";
    w.textContent = waitMsg;
    logBox.appendChild(w);
  }

  // スクロールバーがあるのは logList 自身ではなく、外側の .tabpanel（#panel-log）。
  // logList にスクロール位置を設定しても何も起きないので、親のほうを動かす。
  const logPanel = logBox.parentElement;
  if (logPanel) logPanel.scrollTop = logPanel.scrollHeight;

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

  // 描き終わったので、控えておいた位置と見比べて動きを付ける
  animateCards(cardsBefore);

  renderChooser();
}

/* めくったカードから選ぶ画面。
   候補は自分にしか届かないので、相手の山札の中身は漏れない。 */
function renderChooser() {
  const box = $("chooser");
  const ch = STATE.pending_choice;
  if (!ch) { box.classList.add("hidden"); return; }

  $("chooserTitle").textContent =
    ch.title + (ch.picks > 1 ? "（あと" + ch.picks + "枚）" : "");
  const list = $("chooserCards");
  list.innerHTML = "";
  ch.cards.forEach((c, i) => {
    const el = document.createElement("div");
    el.className = "pickcard" + (RED_SUITS.has(c.suit) ? " red" : "");
    const body = c.kind === "enemy"
      ? '<div class="pick-stats">⚔ ' + c.atk + "　🛡 " + c.dfn + "</div>" +
        '<div class="pick-text">' + escapeHtml(c.ability ? c.ability.text : "技なし") + "</div>"
      : '<div class="pick-text">' + escapeHtml(c.effect ? c.effect.text : "") + "</div>";
    el.innerHTML =
      '<div class="pick-head">' + c.mark + c.rank_label + "</div>" +
      '<div class="pick-name">' + escapeHtml(c.name) + "</div>" + body;
    el.addEventListener("click", () => send({ type: "pick", index: i }));
    list.appendChild(el);
  });
  box.classList.remove("hidden");
}

/* ==================================================== カードの動きの演出
   毎回カードを作り直す方式なので、そのままだと全部パッと入れ替わってしまい、
   何が起きたのか分からない。そこで FLIP（描き直す前後の座標差を使う）で
   「元の場所から今の場所へ動いてきた」ように見せる。

   - 動いた   … 手札→ベンチ、ベンチ→バトル場など。元の位置から滑らせる
   - 出てきた … ふわっと浮かび上がらせる
   - 消えた   … 幽霊を残して2秒かけてゆっくり消す（何が退場したか見える）        */

const MOVE_MS = 1000;   // 移動にかける時間（経路が見える程度に、もたつかない速さ）
const GHOST_MS = 1000;  // 消えるカードが薄れて消えるまでの時間
const CLAW_MS = 1500;   // 爪痕が走って消えるまで（style.css の clawSlash と揃えること）
/* 攻撃側が動き出してから、相手に当たるまでの間。
   同時だと「どちらが殴ったのか」が読み取れないので、
   必ず 揺れ → 少し遅れて爪痕 の順になるように間を空ける。 */
const FX_IMPACT_MS = 250;
const SHAKE_MS = 1000;  // 攻撃モーションの長さ（style.css の attackShake と揃えること）
const FX_HOLD_MAX = 2600;  // どんなに重なってもこれ以上は待たせない

/* エフェクトの再生が終わる時刻。ここまでは次の盤面を出さずに待つ。
   待たずに描くと、前の攻撃の余韻と次の攻撃が重なってしまい、
   お互い同時に殴り合っているように見えてしまう。 */
let fxUntil = 0;
let renderTimer = null;

function noteFx(ms) {
  if (ms > 0) fxUntil = Math.max(fxUntil, Date.now() + Math.min(ms, FX_HOLD_MAX));
}

function renderAfterFx() {
  return new Promise((resolve) => {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    const wait = fxUntil - Date.now();
    if (wait <= 0) { render(); resolve(); return; }
    renderTimer = setTimeout(() => {
      renderTimer = null;
      render();
      resolve();
    }, wait + 40);
  });
}

/* 攻撃モーション・被弾エフェクトは「1回の攻撃につき1回だけ」再生する。
   盤面はカーソル操作などでも描き直されるので、そのたびに揺れないよう
   サーバーから来る fx.seq を見て、まだ再生していないものだけを通す。 */
let lastFxSeq = -1;
let fxFresh = false;

function fxIsNew() { return fxFresh; }

function beginFxFrame() {
  const seq = STATE && STATE.fx ? STATE.fx.seq : null;
  fxFresh = seq != null && seq !== lastFxSeq;
  if (fxFresh) lastFxSeq = seq;
  if (fxFresh) showCallout(STATE.fx);
}

/* 画面上部に、使ったアイテム名や攻撃の口上を大きく出す。
   ログは流れて見落とすので、その瞬間だけ主役を張らせる。

   これは読ませるための表示なので長めに出すが、
   進行は止めない（攻撃モーションは裏で進み、次の手にも移ってよい）。
   fx の待ち時間（animateCards の hold）には含めていない。 */
const CALLOUT_MS = 4000;
let calloutTimer = null;

function showCallout(fx) {
  if (!fx || !fx.title) return;
  const box = $("callout");
  if (!box) return;
  box.className = "callout " + (fx.tone || "buff");
  box.innerHTML = '<div class="callout-title">' + escapeHtml(fx.title) + "</div>" +
    (fx.cry ? '<div class="callout-cry">「' + escapeHtml(fx.cry) + "」</div>" : "");
  // いったん消してから付け直さないと、続けて出したときにアニメが再生されない
  box.classList.remove("show");
  void box.offsetWidth;
  box.classList.add("show");
  if (calloutTimer) clearTimeout(calloutTimer);
  calloutTimer = setTimeout(() => box.classList.remove("show"), CALLOUT_MS);
}

function snapshotCards() {
  const map = {};
  document.querySelectorAll("[data-cardkey]").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;   // 非表示のものは対象外
    map[el.dataset.cardkey] = {
      rect: r,
      code: el.dataset.cardcode || "",
      el: el,
      used: false,
    };
  });
  return map;
}

function animateCards(before) {
  if (!before) return;
  const now = {};
  document.querySelectorAll("[data-cardkey]").forEach((el) => {
    now[el.dataset.cardkey] = el;
  });

  // 今回の描き直しで、いちばん長く残るエフェクトの時間を数えておく。
  // 次の盤面はこれが終わるまで待たせる。
  let hold = fxIsNew() ? Math.max(SHAKE_MS, CLAW_MS) : 0;

  Object.keys(now).forEach((key) => {
    const el = now[key];
    let from = before[key];

    // 手札から場に出た場合はキーが変わる（h♦Q#0 → m12）ので、
    // 「消えた手札のカード」の中から同じカードを探して、そこから動かす。
    if (!from && el.dataset.cardcode) {
      const moved = Object.keys(before).find((k) =>
        !now[k] && !before[k].used && before[k].code &&
        before[k].code === el.dataset.cardcode);
      if (moved) {
        from = before[moved];
        before[moved].used = true;   // これは「消えた」ではなく「動いた」
      }
    }

    // 攻撃モーション中のカードは、揺れと移動が transform を奪い合うので動かさない
    if (el.classList.contains("attacking")) { applyPendingFx(el, FX_IMPACT_MS); return; }

    if (!from) {                      // 新しく出てきたカード
      el.classList.add("card-appear");
      applyPendingFx(el, FX_IMPACT_MS);
      return;
    }

    const to = el.getBoundingClientRect();
    // 中心どうしを合わせる。手札カードと場のカードは大きさが違うので、
    // 左上ではなく中心を基準にしないと、飛び先がずれて見える。
    const dx = (from.rect.left + from.rect.width / 2) - (to.left + to.width / 2);
    const dy = (from.rect.top + from.rect.height / 2) - (to.top + to.height / 2);
    const scale = to.width > 0 ? from.rect.width / to.width : 1;
    const scaled = Math.abs(scale - 1) > 0.05;
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2 && !scaled) {   // 動いていない
      applyPendingFx(el, FX_IMPACT_MS);
      return;
    }

    // いったん元の位置・元の大きさに戻してから、本来の姿へ滑らせる
    el.style.transition = "none";
    el.style.transformOrigin = "50% 50%";
    el.style.transform =
      "translate(" + dx + "px, " + dy + "px)" + (scaled ? " scale(" + scale + ")" : "");
    // 抜け殻(#ghostLayer=18)や他のカードより手前を通す。移動が隠れないように。
    el.style.zIndex = "35";
    requestAnimationFrame(() => {
      el.style.transition = "transform " + MOVE_MS + "ms cubic-bezier(.25,.6,.3,1)";
      el.style.transform = "";
      setTimeout(() => {
        el.style.transition = "";
        el.style.zIndex = "";
        el.style.transformOrigin = "";
      }, MOVE_MS + 40);
    });
    // 移動しきってからダメージを受ける
    applyPendingFx(el, MOVE_MS + 60);
    // 移動そのもの＋そのあと走る爪痕までが今回の見せ場
    hold = Math.max(hold, MOVE_MS + (el.dataset.fxafter ? CLAW_MS : 0));
  });

  // 場から消えたカードは、抜け殻をその場に残してゆっくり薄れさせる
  Object.keys(before).forEach((key) => {
    if (now[key] || before[key].used) return;
    spawnGhost(before[key]);
    hold = Math.max(hold, GHOST_MS);
  });

  noteFx(hold + 120);   // 少し余韻を残してから次の盤面へ
}

/* 控えておいた被弾演出（点滅・爪痕）を実際に発動させる。
   カードが動いた場合は、動き終わるのを待ってから斬られるようにする。 */
function applyPendingFx(el, delay) {
  const cls = el.dataset.fxafter;
  if (!cls) return;
  delete el.dataset.fxafter;   // 二重に発動させない
  const go = () => {
    // 待っている間に描き直されて、この要素が捨てられていることがある
    if (!el.isConnected) return;
    cls.split(" ").forEach((c) => { if (c) el.classList.add(c); });
  };
  if (delay > 0) setTimeout(go, delay);
  else requestAnimationFrame(go);
}

function ghostLayer() {
  let layer = $("ghostLayer");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "ghostLayer";
    document.body.appendChild(layer);
  }
  return layer;
}

function spawnGhost(info) {
  const r = info.rect;
  const g = info.el.cloneNode(true);
  g.removeAttribute("data-cardkey");     // 次のスナップショットで拾われないように
  g.classList.add("card-ghost");

  // 攻撃で倒されたカードは、抜け殻に爪痕を刻んでから薄れさせる。
  // 倒れたカードは盤面から消えてしまうので、こうしないと
  // 「斬られて倒れた」のか「勝手に消えた」のか分からない。
  if (fxIsNew() && STATE.fx && STATE.fx.target != null &&
      info.el.dataset.cardkey === "m" + STATE.fx.target) {
    g.classList.add("clawed");
    if (!g.querySelector(".claw")) {
      const claw = document.createElement("div");
      claw.className = "claw";
      g.appendChild(claw);
    }
  }
  g.style.left = r.left + "px";
  g.style.top = r.top + "px";
  g.style.width = r.width + "px";
  g.style.height = r.height + "px";
  ghostLayer().appendChild(g);
  requestAnimationFrame(() => g.classList.add("fading"));
  setTimeout(() => g.remove(), GHOST_MS + 120);
}

function optionSummary() {
  const o = (STATE && STATE.options) || {};
  const off = [];
  if (!o.enemy_abilities) off.push("技なし");
  else if (!o.demon_lord) off.push("魔王なし");
  return off.length ? "⚙️ " + off.join("・") : "";
}

/* 攻撃ボタンが押せないとき、その理由を書いた文言を返す。
   「疲労で撃てない」のか「もう撃った」のかは盤面から読み取りにくいので、
   ボタンそのものに書いてしまうのが一番分かりやすい。
   判定の順番は engine の legal_actions と同じにしてある。 */
function attackBlockedLabel(st, me) {
  if (!st.is_my_turn) return "⚔️ 攻撃（相手の番）";
  if (!me.battle) return "⚔️ 攻撃（バトル場が空）";
  if (me.attacked) return "✅ このターンは攻撃済み";
  if (me.battle.fatigue > 0) {
    return "😴 疲労中（あと" + me.battle.fatigue + "ターン攻撃できない）";
  }
  return "⚔️ 攻撃（いまは攻撃できない）";
}

/* ログの末尾に出す「いま何を待っているか」の1行。
   進行が止まって見えるとき、誰の操作待ちなのかが分かるようにする。 */
function waitingText(st, op) {
  if (st.winner !== null && st.winner !== undefined) return "";
  const pend = st.pending_promote;
  if (pend !== null && pend !== undefined) {
    return pend === st.viewer
      ? "⏳ バトル場へ出すカードを選んでください…"
      : "⏳ " + op.name + " がバトル場へ出すカードを選んでいます…";
  }
  if (!st.is_my_turn) {
    return "⏳ " + op.name + " が「ターン終了」を押すのを待っています…";
  }
  return "⏳ あなたが「ターン終了」を押すのを待っています…";
}

function hintText(st, me, byType) {
  if (st.winner !== null && st.winner !== undefined) return "ゲーム終了";

  // バトル場の繰り上げ待ちは、手番より優先して案内する
  if (st.pending_promote === st.viewer) {
    return "🔀 バトル場が空きました！デッキから出すエネミーをクリックしてね";
  }
  if (st.pending_promote !== null && st.pending_promote !== undefined) {
    return "⏳ 相手がバトル場に出すエネミーを選んでいます…";
  }

  if (!st.is_my_turn) {
    return st.room && st.room.mode === "lan"
      ? "相手の番です。待ってね…" : "CPUが考え中…";
  }
  // できる事が何も残っていないなら、真っ先にそれを伝える
  const canDoSomething = (byType.attack || []).length || (byType.place || []).length ||
                         (byType.item || []).length || (byType.swap || []).length;
  if (!canDoSomething && (byType.end_turn || []).length) {
    return "👉 もうできる事はありません。「ターン終了」を押してね";
  }

  // 攻撃を残したまま終わりそうなときは、それを最優先で知らせる。
  // 攻撃ボタンは無くしたので、どこを押せば攻撃できるかもここで案内する。
  if (st.attack_chance === "after_swap") {
    return "⚠️ バトル場は攻撃できないけど、デッキをクリックして交代すればまだ攻撃できるよ";
  }
  if (st.attack_chance === "now") {
    return "⚔️ バトル場の自分のカードをクリックで攻撃！";
  }

  const bits = [];
  // 攻撃できない理由は、盤面を見ても分かりにくいので言葉で出す
  if (me.attacked) bits.push("✅ このターンは攻撃済み");
  else if (me.battle && me.battle.fatigue > 0) {
    bits.push("😴 バトル場は疲労中（あと" + me.battle.fatigue + "ターン）");
  }
  if ((byType.place || []).length) bits.push("🃏 配置できるエネミーがいます");
  if (me.item_used) bits.push("アイテムは使用済み");
  if (me.swaps_left <= 0) bits.push("交代は使用済み");
  if (me.attacked) bits.push("⏭️ 終わったら「ターン終了」を押してね");
  return bits.join(" / ") || "行動を選んでね";
}

function fill(box, list, opts) {
  box.innerHTML = "";
  list.forEach((m, i) => {
    const merged = Object.assign({}, opts, { flash: flashClass(m) });
    if (opts && opts.trackPrefix) merged.trackKey = opts.trackPrefix + i;
    box.appendChild(enemyCard(m, merged));
  });
}

function pct(v, max) {
  return Math.max(0, Math.min(100, (v / max) * 100)) + "%";
}

/* ------------------------------------------------- ダメージ/回復の点滅 */
// エネミーのHPを前回の描画と比べて、"hit"（減った）/"heal"（増えた）を返す。
// 呼ぶたびに記録も更新するので、同じエネミーについて1回だけ呼ぶこと。
function flashClass(m) {
  if (!m) return null;
  const prev = prevHp[m.uid];
  let cls = null;
  if (prev !== undefined) {
    if (m.hp < prev) cls = "hit";
    else if (m.hp > prev) cls = "heal";
  }
  prevHp[m.uid] = m.hp;
  return cls;
}

// すでにDOMにある要素（トレーナー枠など）にアニメーションクラスを付け直す。
// 同じクラス名を続けて付けても再生されないブラウザの仕様があるので、
// 一度外してから（リフローを挟んで）付け直す。
function pulse(el, cls) {
  el.classList.remove("hit", "heal");
  if (!cls) return;
  void el.offsetWidth;   // 強制リフロー：これがないとアニメーションが再生されないことがある
  el.classList.add(cls);
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
    $("refRules").innerHTML = CardRef.rulesHtml(REF);
    $("refItem").innerHTML = CardRef.itemHtml(REF, false);
    $("refEnemy").innerHTML = CardRef.enemyHtml(REF, false);
  } catch (e) {
    $("refRules").innerHTML = '<div class="ref-note">読み込みに失敗しました: ' + e.message + "</div>";
    $("refItem").innerHTML = '<div class="ref-note">読み込みに失敗しました: ' + e.message + "</div>";
  }
}

/* ==================================================== 名前の変更 */
function openNameDialog() {
  if (!SESSION || !STATE || !STATE.me) return;
  $("newName").value = STATE.me.name || "";
  $("nameOverlay").classList.remove("hidden");
  $("newName").focus();
  $("newName").select();
}

async function applyName() {
  const name = ($("newName").value || "").trim();
  if (!name) { showToast("名前を入れてね。"); return; }
  try {
    STATE = await api("/api/room/rename",
      { code: SESSION.code, token: SESSION.token, name: name });
    localStorage.setItem(NAME_KEY, name);
    $("nameOverlay").classList.add("hidden");
    lastRev = -1;
    render();
  } catch (e) { showToast(e.message); }
}

/* ======================================================= オプション */
let pendingLevel = "normal";   // オプション画面で選び中のCPUの強さ
let SKIN_INFO = null;          // { skins: [...], current_skin: "arcana" }（初回だけ取得）

function openOptions() {
  const o = (STATE && STATE.options) || {};
  $("optAbilities").checked = !!o.enemy_abilities;
  $("optDemon").checked = !!o.demon_lord;
  syncOptionLock();

  const isCpu = !!(STATE && STATE.room && STATE.room.mode === "cpu");
  $("optLevelBlock").classList.toggle("hidden", !isCpu);
  if (isCpu) selectLevel((STATE.room.cpu_level) || "normal");

  loadSkinOptions();
  $("optionOverlay").classList.remove("hidden");
}

async function loadSkinOptions() {
  try {
    if (!SKIN_INFO) SKIN_INFO = await api("/api/options");
    renderSkinButtons(SKIN_INFO.current_skin);
  } catch (e) { /* 取得できなくてもオプション画面自体は開けるようにしておく */ }
}

function renderSkinButtons(activeId) {
  const box = $("optSkins");
  if (!SKIN_INFO || !SKIN_INFO.skins) return;
  box.innerHTML = "";
  SKIN_INFO.skins.forEach((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "levelbtn" + (s.id === activeId ? " active" : "");
    b.textContent = s.label;
    b.dataset.skin = s.id;
    b.addEventListener("click", () => selectSkin(s.id));
    box.appendChild(b);
  });
}

async function selectSkin(skinId) {
  try {
    const r = await api("/api/skin", { skin: skinId });
    SKIN_INFO.current_skin = skinId;
    renderSkinButtons(skinId);
    showToast(r.message || "スキンを切り替えました。");
  } catch (e) { showToast(e.message); }
}

function syncOptionLock() {
  const on = $("optAbilities").checked;
  $("optDemon").disabled = !on;
  if (!on) $("optDemon").checked = false;
}

function selectLevel(level) {
  pendingLevel = level;
  document.querySelectorAll(".levelbtn").forEach((b) => {
    b.classList.toggle("active", b.dataset.level === level);
  });
}

async function applyOptions() {
  $("optionOverlay").classList.add("hidden");
  const isCpu = !!(STATE && STATE.room && STATE.room.mode === "cpu");
  await rematch({
    enemy_abilities: $("optAbilities").checked,
    demon_lord: $("optAbilities").checked && $("optDemon").checked,
  }, isCpu ? pendingLevel : null);
}

/* ============================================================== 起動 */
$("endTurnBtn").addEventListener("click", () => {
  // 攻撃は1ターンに1回きり。使わずに終わるのはもったいないので引き止める。
  // 「交代すれば撃てる」場合も対象（交代しても攻撃権は残るため）。
  // どう頑張っても撃てないターンは、聞いても仕方がないので黙って終了する。
  const chance = STATE.attack_chance;
  if (chance) {
    const msg = chance === "after_swap"
      ? "まだ攻撃していません。\nデッキと交代すれば、このターンまだ攻撃できます。\n\nこのままターンを終了しますか？"
      : "まだ攻撃していません。\n\nこのままターンを終了しますか？";
    if (!confirm(msg)) return;
  }
  send({ type: "end_turn" });
});
$("newGameBtn").addEventListener("click", () => rematch(null));
$("ovBtn").addEventListener("click", () => rematch(null));
$("leaveBtn").addEventListener("click", leaveRoom);
$("optionBtn").addEventListener("click", openOptions);
$("optCancel").addEventListener("click", () => $("optionOverlay").classList.add("hidden"));
$("optApply").addEventListener("click", applyOptions);
$("optAbilities").addEventListener("change", syncOptionLock);
document.querySelectorAll(".levelbtn").forEach((b) => {
  b.addEventListener("click", () => selectLevel(b.dataset.level));
});
$("sheetClose").addEventListener("click", closeSheet);
$("sheetAction").addEventListener("click", () => {
  const a = sheetAction;
  closeSheet();
  if (a) a();
});
$("cardSheet").addEventListener("click", (e) => {
  if (e.target === $("cardSheet")) closeSheet();   // 外側をタップで閉じる
});

$("btnCpu").addEventListener("click", () => showLobby("lb-cpulevel"));
$("cpuLevelModes").addEventListener("click", (e) => {
  const b = e.target.closest(".modecard");
  if (b) createRoom("cpu", b.dataset.level);
});
$("btnLan").addEventListener("click", () => {
  const saved = localStorage.getItem(NAME_KEY);
  if (saved) $("playerName").value = saved;
  showLobby("lb-lan");
});
$("btnMakeRoom").addEventListener("click", () => {
  localStorage.setItem(NAME_KEY, playerName());
  createRoom("lan");
});
$("btnFindRoom").addEventListener("click", () => {
  localStorage.setItem(NAME_KEY, playerName());
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
    // 作りかけのLAN部屋から抜けるだけ。中断した対戦（RESUMABLE）はそのまま残す。
    // サーバー側の部屋も閉じておかないと、一覧にゴミが残り続ける。
    if (SESSION && SESSION.mode === "lan") {
      const s = SESSION;
      api("/api/room/leave", { code: s.code, token: s.token }).catch(() => {});
      SESSION = null;
      saveSession();
      stopPolling();
    }
    showLobby(b.dataset.back);
  });
});

$("btnResume").addEventListener("click", resumeGame);
$("myName").addEventListener("click", openNameDialog);
$("nameApply").addEventListener("click", applyName);
$("nameCancel").addEventListener("click", () => $("nameOverlay").classList.add("hidden"));
$("newName").addEventListener("keydown", (e) => {
  if (e.key === "Enter") applyName();
  if (e.key === "Escape") $("nameOverlay").classList.add("hidden");
});

/* モード選択の外側をタップしたら、中断した対戦にもどる。
   「間違えてモード選択を開いてしまった」を1タップで取り消せるように。 */
$("lobby").addEventListener("click", (e) => {
  if (e.target !== $("lobby")) return;             // 中身のタップは無視
  if (!$("lb-mode").classList.contains("active")) return;
  if (RESUMABLE) resumeGame();
});

// スクロールやウィンドウサイズ変更で位置がずれるので、いったん消す
window.addEventListener("scroll", hideHoverPop, true);
window.addEventListener("resize", hideHoverPop);

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
