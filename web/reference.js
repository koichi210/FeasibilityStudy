/* カード図鑑の描画。
   ゲーム画面の右パネル（タブ）と、単独ページ /cards の両方から使う。

   見せ方の方針：52枚をそのまま並べても覚えられない。
   数字カードはスートごとに規則的なので「4つの規則 ＋ 絵札16枚」の形で見せる。 */

(function (global) {
  "use strict";

  const RED = { H: true, D: true };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function suitCls(s) {
    return RED[s] ? "ref-red" : "ref-black";
  }

  /* -------------------------------------------------------------- ルール */
  function rulesHtml(ref) {
    const c = ref.constants;
    let h = "";

    h += '<div class="ref-lead">🏁 <b>勝利条件</b></div>';
    h += '<div class="ref-note">相手のトレーナーHPを0にしたら勝ち。トレーナーHPは <b>' +
           c.trainer_hp + "</b>。</div>";

    h += '<div class="ref-lead">🏟️ <b>場の構成</b></div>';
    h += '<div class="ref-note">バトル場1枚＋デッキ<b>' + c.bench_size + "</b>枚。" +
           "バトル場のエネミーだけが攻撃・被攻撃の対象になる。</div>";

    h += '<div class="ref-lead">🃏 <b>エネミーの配置</b></div>';
    h += '<div class="ref-note">場が空くと、山札から自動で「ベンチ」にカードが来る。<br>' +
           "<b>クリックして選び、空いている枠をクリックすると配置</b>される（回数制限なし）。<br>" +
           "ゲーム開始時の最初の配置だけは、先攻・後攻が不公平にならないよう自動で場に出る。</div>";

    h += '<div class="ref-lead">😴 <b>疲労と強制退場</b></div>';
    h += '<div class="ref-note">攻撃すると疲労し、次の自分のターンは攻撃できない' +
           "（" + c.fatigue_turns + "ターンで回復）。<br>" +
           "合計<b>" + c.attacks_before_retire + "回攻撃</b>したら、HPが残っていても強制退場する。</div>";

    h += '<div class="ref-lead">⚔️ <b>ダメージ計算</b></div>';
    h += '<div class="ref-note">ダメージ ＝ 攻撃力 － 相手の防御力（最低 <b>' + c.min_damage +
           "</b> は必ず通る）。<br>エネミーのHPは全員共通で <b>" + c.enemy_hp + "</b>。</div>";

    h += '<div class="ref-lead">💥 <b>トレーナーへのダメージ</b></div>';
    h += '<div class="ref-note">自分のエネミーが<b>相手に倒された</b>とき <b>' +
           c.kill_trainer_damage + "</b>ダメージ。<br>" +
           "相手の場が空のときに<b>直接攻撃</b>すると、攻撃力そのままダメージが入る。</div>";

    h += '<div class="ref-lead">🎒 <b>アイテム</b></div>';
    h += '<div class="ref-note">両者共有のアイテムデッキから、毎ターン' + c.item_draw_per_turn +
           "枚ドロー（手札上限" + c.hand_size_max + "枚）。<br><b>1ターンに1枚まで</b>使用できる。</div>";

    h += '<div class="ref-lead">👹 <b>魔王</b></div>';
    h += '<div class="ref-note">♠A「魔王降臨」を出すと、HP・攻撃・防御が圧倒的な魔王に変身。<br>' +
           esc(ref.enemy.demon.text) + "</div>";

    h += '<div class="ref-lead">⚙️ <b>ゲームオプション</b></div>';
    h += '<div class="ref-note">「エネミーの技」「魔王」のON/OFF、CPUの強さ（🐣初級／⚔️中級／🔥上級）は、' +
           "右上の⚙️オプションからいつでも変更できる。</div>";

    return h;
  }

  /* ---------------------------------------------------------- アイテム */
  function itemHtml(ref, full) {
    const d = ref.item;
    let h = "";

    h += '<div class="ref-lead">📌 <b>数字カード（2〜10）は、この4つの規則だけ</b>で全部わかる</div>';
    h += '<div class="ref-rules">';
    d.suit_rules.forEach((r) => {
      h += '<div class="ref-rule ' + suitCls(r.suit) + '">' +
             '<div class="ref-rule-head"><span class="ref-mark">' + r.mark + "</span>" +
               '<span class="ref-role">' + esc(r.role) + "</span></div>" +
             '<div class="ref-rule-body">' + esc(r.rule) + "</div>" +
             '<div class="ref-rule-eg">' + esc(r.example) + "</div>" +
           "</div>";
    });
    h += "</div>";

    h += '<div class="ref-lead">🎴 <b>覚えるのは、あとは絵札16枚だけ</b></div>';
    h += faceTable(d.faces, false);

    // 数字カードも名前で呼びたいので、パネルでも常に一覧を出す
    h += '<div class="ref-lead">🔢 数字カードの一覧（2〜10）</div>';
    h += numberTable(d.numbers, false);
    return h;
  }

  /* -------------------------------------------------------- エネミー */
  function enemyHtml(ref, full) {
    const d = ref.enemy;
    const c = ref.constants;
    let h = "";

    h += '<div class="ref-lead">📌 <b>スートで役割が決まる</b>。強さは数字に比例</div>';
    h += '<div class="ref-rules">';
    d.suit_rules.forEach((r) => {
      h += '<div class="ref-rule ' + suitCls(r.suit) + '">' +
             '<div class="ref-rule-head"><span class="ref-mark">' + r.mark + "</span>" +
               '<span class="ref-role">' + esc(r.role) + "</span></div>" +
             '<div class="ref-rule-body">⚔ ' + esc(r.atk_formula) +
               "　🛡 " + esc(r.def_formula) + "</div>" +
             '<div class="ref-rule-eg">' + esc(r.hint) + "</div>" +
           "</div>";
    });
    h += "</div>";

    h += '<div class="ref-note">' +
           "HPは全エネミー共通で <b>" + c.enemy_hp + "</b>。" +
           "ダメージは <b>攻撃 − 相手の防御</b>（最低 " + c.min_damage + " は必ず通る）。<br>" +
           "<b>" + c.attacks_before_retire + "回攻撃したら強制退場</b>。倒されると自分のトレーナーに " +
           c.kill_trainer_damage + " ダメージ。" +
         "</div>";

    h += '<div class="ref-lead">🎴 <b>絵札16枚だけが特殊能力を持つ</b></div>';
    h += faceTable(d.faces, true);

    h += '<div class="ref-lead">👹 <b>魔王</b></div>';
    h += '<div class="ref-demon">' +
           "<b>HP " + d.demon.hp + " / ⚔ " + d.demon.atk + " / 🛡 " + d.demon.def + "</b><br>" +
           esc(d.demon.text) +
         "</div>";

    // 数字カードも名前で呼びたいので、パネルでも常に一覧を出す
    h += '<div class="ref-lead">🔢 数字カードの一覧（2〜10）</div>';
    h += numberTable(d.numbers, true);
    return h;
  }

  /* ------------------------------------------------------------ 表の生成 */
  function faceTable(groups, isEnemy) {
    let h = "";
    groups.forEach((g) => {
      h += '<div class="ref-group ' + suitCls(g.suit) + '">';
      h += '<div class="ref-group-head"><span class="ref-mark">' + g.mark + "</span> " +
             esc(g.name) + '<span class="ref-group-role">' + esc(g.role) + "</span></div>";
      h += '<table class="ref-table"><tbody>';
      g.cards.forEach((c) => {
        h += "<tr>";
        h += '<td class="ref-c">' + c.mark + c.rank_label + "</td>";
        h += '<td class="ref-n">' + esc(c.name) + "</td>";
        if (isEnemy) {
          h += '<td class="ref-s">⚔' + c.atk + " 🛡" + c.dfn + "</td>";
          h += '<td class="ref-t">' + esc(c.ability ? c.ability.text : "—") + "</td>";
        } else {
          h += '<td class="ref-t" colspan="2">' + esc(stripName(c.text)) + "</td>";
        }
        h += "</tr>";
      });
      h += "</tbody></table></div>";
    });
    return h;
  }

  function numberTable(groups, isEnemy) {
    let h = '<div class="ref-numgrid">';
    groups.forEach((g) => {
      h += '<div class="ref-group ' + suitCls(g.suit) + '">';
      h += '<div class="ref-group-head"><span class="ref-mark">' + g.mark + "</span> " +
             esc(g.name) + "</div>";
      h += '<table class="ref-table"><tbody>';
      g.cards.forEach((c) => {
        h += "<tr><td class=\"ref-c\">" + c.mark + c.rank_label + "</td>";
        if (isEnemy) {
          h += '<td class="ref-n">' + esc(c.name) + "</td>";
          h += '<td class="ref-s">⚔' + c.atk + " 🛡" + c.dfn + "</td>";
        } else {
          h += '<td class="ref-t">' + esc(stripName(c.text)) + "</td>";
        }
        h += "</tr>";
      });
      h += "</tbody></table></div>";
    });
    return h + "</div>";
  }

  /** 「薬草：バトル場のHPを70回復」→「バトル場のHPを70回復」 */
  function stripName(text) {
    const i = String(text).indexOf("：");
    return i >= 0 ? text.slice(i + 1) : text;
  }

  global.CardRef = { rulesHtml: rulesHtml, itemHtml: itemHtml, enemyHtml: enemyHtml, esc: esc };
})(window);
