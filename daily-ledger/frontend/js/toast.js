/**
 * toast.js — Bootstrap Toast 訊息提示（右上角，3 秒自動消失）
 * 依賴：頁面需含 id="toastContainer" 的 div
 */
const toast = (() => {
  function show(message, type = "success") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const id = `toast-${Date.now()}`;
    const iconClass = type === "success" ? "bi-check-circle-fill text-success"
                                         : "bi-exclamation-triangle-fill text-danger";
    const safeMsg = String(message)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const html = `
      <div id="${id}" class="toast align-items-center border-0 mb-2" role="alert" aria-live="assertive">
        <div class="d-flex">
          <div class="toast-body d-flex align-items-center gap-2">
            <i class="bi ${iconClass}"></i>
            <span>${safeMsg}</span>
          </div>
          <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
      </div>`;
    container.insertAdjacentHTML("beforeend", html);

    const el = document.getElementById(id);
    const bsToast = new bootstrap.Toast(el, { delay: 3000 });
    bsToast.show();
    el.addEventListener("hidden.bs.toast", () => el.remove());
  }

  return {
    success: (msg) => show(msg, "success"),
    error:   (msg) => show(msg, "error"),
  };
})();
