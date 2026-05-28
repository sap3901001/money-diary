/**
 * navbar.js — 依當前 URL 動態設定 navbar active 狀態
 */
(function () {
  const path = location.pathname.replace(/\/$/, "") || "/index.html";
  document.querySelectorAll(".nav-link[data-page]").forEach(link => {
    const page = link.dataset.page;
    const active =
      (page === "index" && (path === "" || path === "/" || path.endsWith("index.html"))) ||
      (page !== "index" && path.endsWith(page + ".html"));
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
  });
})();
