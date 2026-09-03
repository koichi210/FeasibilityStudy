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

    if (full) {
      h += '<div class="ref-lead">🔢 数字カードの一覧（規則どおりなので、確認用）</div>';
      h += numberTable(d.numbers, false);
    }
    return h;
  }

  /* -------------------------------------------------------- モンスター */
  function monsterHtml(ref, full) {
    const d = ref.monster;
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
           "HPは全モンスター共通で <b>" + c.monster_hp + "</b>。" +
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

    if (full) {
      h += '<div class="ref-lead">🔢 数字カードの一覧（計算どおりなので、確認用）</div>';
      h += numberTable(d.numbers, true);
    }
    return h;
  }

  /* ------------------------------------------------------------ 表の生成 */
  function faceTable(groups, isMonster) {
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
        if (isMonster) {
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

  function numberTable(groups, isMonster) {
    let h = '<div class="ref-numgrid">';
    groups.forEach((g) => {
      h += '<div class="ref-group ' + suitCls(g.suit) + '">';
      h += '<div class="ref-group-head"><span class="ref-mark">' + g.mark + "</span> " +
             esc(g.name) + "</div>";
      h += '<table class="ref-table"><tbody>';
      g.cards.forEach((c) => {
        h += "<tr><td class=\"ref-c\">" + c.mark + c.rank_label + "</td>";
        if (isMonster) {
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

  global.CardRef = { itemHtml: itemHtml, monsterHtml: monsterHtml, esc: esc };
})(window);
