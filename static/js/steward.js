// "My points": the boxes this browser looks after. Refreshes every few seconds and
// shows an in-app alert when one of them becomes empty (a simulated notification:
// no real push, no account). /steward?watch=krk-demo adds a point, handy for the demo.
import { getPoints, postEvent } from "./api.js";
import "./pwa.js";
import { dotSvg } from "./dot.js";
import { setupHeader } from "./header.js";
import { initI18n, t, timeAgo } from "./i18n.js";
import { getWatched, setWatched } from "./watch.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const REFRESH_MS = 8000;

let points = new Map();       // id -> point (only the watched ones)
const lastStatus = new Map(); // id -> status at the previous refresh
const alerts = new Map();     // id -> true while an alert is shown

function card(p) {
  const needsRefill = p.status === "empty" || p.status === "low";
  return `
    <li class="card watch-item ${needsRefill ? "needs-refill" : ""}">
      <div class="status-row">
        ${dotSvg(p.status, { size: 36, faded: p.confidence === "faded" })}
        <div>
          <p class="place-name">${esc(p.name)}</p>
          <p class="muted">${esc(t(`status.${p.status}`))} · ${esc(p.last_confirmed_at
            ? t("point.confirmed", { ago: timeAgo(p.minutes_since_confirmed) }) : t("point.never"))}</p>
        </div>
      </div>
      <div class="sheet-actions">
        <button class="btn" type="button" data-refill="${esc(p.id)}">${esc(t("action.refilled"))}</button>
        <a class="btn secondary" href="/?p=${encodeURIComponent(p.id)}">${esc(t("point.open_map"))}</a>
        <button class="link-btn" type="button" data-unwatch="${esc(p.id)}">${esc(t("watch.off"))}</button>
      </div>
    </li>`;
}

function renderList() {
  const ids = getWatched();
  $("empty-state").hidden = ids.length > 0;
  $("list").innerHTML = ids.map((id) => points.get(id)).filter(Boolean).map(card).join("");
}

function renderAlerts() {
  $("alerts").innerHTML = [...alerts.keys()].map((id) => {
    const p = points.get(id);
    if (!p) return "";
    return `
      <div class="alert-banner">
        ${dotSvg("empty", { size: 28 })}
        <p><strong>${esc(p.name)}</strong><br>${esc(t("steward.alert"))}</p>
        <button class="btn" type="button" data-refill="${esc(id)}">${esc(t("action.refilled"))}</button>
      </div>`;
  }).join("");
  document.title = alerts.size ? `(${alerts.size}) ${t("steward.title")} · Kropka` : `${t("steward.title")} · Kropka`;
}

async function refresh() {
  try {
    const data = await getPoints("krakow");
    const watched = new Set(getWatched());
    points = new Map(data.points.filter((p) => watched.has(p.id)).map((p) => [p.id, p]));
  } catch {
    return; // offline: keep showing the last list
  }
  for (const p of points.values()) {
    const before = lastStatus.get(p.id);
    // Alert only on a CHANGE to empty, not for boxes that were already empty when the page opened.
    if (before && before !== "empty" && p.status === "empty") {
      alerts.set(p.id, true);
      navigator.vibrate?.([120, 60, 120]);
    }
    if (p.status !== "empty") alerts.delete(p.id);
    lastStatus.set(p.id, p.status);
  }
  renderList();
  renderAlerts();
}

async function onClick(e) {
  const refillId = e.target.closest("[data-refill]")?.dataset.refill;
  const unwatchId = e.target.closest("[data-unwatch]")?.dataset.unwatch;
  if (refillId) {
    e.target.disabled = true;
    $("message").hidden = true;
    try {
      await postEvent(refillId, "refilled", "steward");
      alerts.delete(refillId);
    } catch (err) {
      const key = `error.${err.code}`;
      $("message").textContent = t(key) === key ? t("error.generic") : t(key);
      $("message").hidden = false;
    }
    await refresh();
  }
  if (unwatchId) {
    setWatched(unwatchId, false);
    alerts.delete(unwatchId);
    await refresh();
  }
}

async function main() {
  setupHeader();
  await initI18n();
  // Demo helper: /steward?watch=krk-demo
  const add = new URLSearchParams(location.search).get("watch");
  if (add) {
    setWatched(add, true);
    history.replaceState(null, "", "/steward");
  }
  document.querySelector("main").addEventListener("click", onClick);
  document.addEventListener("langchange", () => { renderList(); renderAlerts(); });
  await refresh();
  setInterval(() => { if (document.visibilityState === "visible") refresh(); }, REFRESH_MS);
}

main();
