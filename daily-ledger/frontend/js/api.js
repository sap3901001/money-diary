/**
 * api.js — fetch 包裝，統一錯誤處理、JSON parse
 */
const api = (() => {
  async function _fetch(url, options = {}) {
    const hasBody = options.body !== undefined;
    const res = await fetch(url, {
      ...(hasBody && { headers: { "Content-Type": "application/json" } }),
      ...options,
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = data?.detail || `HTTP ${res.status}`;
      throw new Error(Array.isArray(msg)
        ? msg.map(e => e.msg.replace(/^Value error,\s*/i, "")).join("；")
        : msg);
    }
    return data;
  }

  return {
    get:    (url)         => _fetch(url),
    post:   (url, body)   => _fetch(url, { method: "POST",   body: JSON.stringify(body) }),
    put:    (url, body)   => _fetch(url, { method: "PUT",    body: JSON.stringify(body) }),
    delete: (url, body)   => _fetch(url, { method: "DELETE", body: body ? JSON.stringify(body) : undefined }),
  };
})();
