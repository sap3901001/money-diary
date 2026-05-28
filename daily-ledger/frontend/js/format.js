/**
 * format.js — 格式化函式
 */
const fmt = (() => {
  function amount(n) {
    return Number(n).toLocaleString("zh-TW");
  }

  function amountSigned(n, type) {
    const val = amount(Math.abs(n));
    return type === "I" ? `+${val}` : `-${val}`;
  }

  // YYYY-MM-DD → MM/DD
  function dateShort(s) {
    if (!s) return "";
    const [, m, d] = s.split("-");
    return `${m}/${d}`;
  }

  function typeLabel(t) {
    return t === "I" ? "收入" : "支出";
  }

  function typeBadge(t) {
    const cls = t === "I" ? "badge-income" : "badge-expense";
    return `<span class="badge ${cls}">${typeLabel(t)}</span>`;
  }

  function categoryLabel(main, sub) {
    return sub ? `${main} / ${sub}` : main;
  }

  // HTML 轉義（供各頁面共用，避免各自複製貼上）
  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  return { amount, amountSigned, dateShort, typeLabel, typeBadge, categoryLabel, escHtml };
})();
