// 汎用ヘルパー。他のモジュールに依存しない。
// ※ file:// で直接開いても動くように、ES Modules ではなく通常の<script>読み込み＋
//   グローバルの KG 名前空間にぶら下げる方式にしている。

(function () {
  window.KG = window.KG || {};

  let idCounter = 1;

  /** ユニット/構造物に振る一意なID */
  function uid(prefix) {
    idCounter += 1;
    return `${prefix}-${idCounter}`;
  }

  /** マンハッタン距離（射程・移動コストの計算に使う） */
  function manhattan(r1, c1, r2, c2) {
    return Math.abs(r1 - r2) + Math.abs(c1 - c2);
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  window.KG.util = { uid, manhattan, clamp };
})();
