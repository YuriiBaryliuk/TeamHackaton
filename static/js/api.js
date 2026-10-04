// Tiny wrapper around fetch for our JSON API.
// Errors from the server look like {detail: {code, message}}; we turn them into
// an ApiError with a stable `code` that i18n can translate ("error.<code>").

export class ApiError extends Error {
  constructor(status, code, detail) {
    super(detail?.message || code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError(0, "network");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof body?.detail === "object" && !Array.isArray(body.detail) ? body.detail : null;
    throw new ApiError(res.status, detail?.code || "generic", detail);
  }
  return body;
}

export const getPoints = (city = "krakow") => api(`/api/points?city=${encodeURIComponent(city)}`);

export const getPoint = (id) => api(`/api/points/${encodeURIComponent(id)}`);

export const postEvent = (id, type, source = "qr") =>
  api(`/api/points/${encodeURIComponent(id)}/events`, {
    method: "POST",
    body: JSON.stringify({ type, source }),
  });

export const getPointStats = (id, days = 30) => api(`/api/points/${encodeURIComponent(id)}/stats?days=${days}`);

export const postNewPoint = (data) => api("/api/points", { method: "POST", body: JSON.stringify(data) });

export const postUrgent = (lat, lon) =>
  api("/api/urgent", { method: "POST", body: JSON.stringify({ lat, lon }) });
