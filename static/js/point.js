// QR landing page /p/{id}: show the point's status and the three big buttons.
// No map library here, so the page loads fast on a phone.
import { getPoint, postEvent } from "./api.js";
import "./pwa.js";
import { dotSvg } from "./dot.js";
import { initI18n, renderLangSwitch, t, timeAgo } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const pointId = decodeURIComponent(location.pathname.split("/p/")[1] || "").replace(/\/$/, "");

let point = null;       // latest data from the server
let lastAction = null;  // what the user just did, for the thank-you text

function statusWords(p) {
  if (p.status === "unknown" && !p.has_products && p.confidence === "none") return t("status.no_products");
  return t(`status.${p.status}`);
}

function render() {
  if (!point) return;
  const faded = point.confidence === "faded";
  $("loading").hidden = true;
  $("point-info").hidden = false;
  $("demo-badge").hidden = !point.is_demo;
  $("point-name").textContent = point.name;
  $("point-address").textContent = point.address || "";
  $("status-dot").innerHTML = dotSvg(point.status, { size: 44, faded });
  $("status-text").textContent = statusWords(point);
  $("status-ago").textContent = point.last_confirmed_at
    ? `${t("point.confirmed", { ago: timeAgo(point.minutes_since_confirmed) })}${faded ? ` · ${t("freshness.faded")}` : ""}`
    : t("point.never");
  $("point-meta").textContent = [
    t(`access.${point.access}`),
    t(point.open_now ? "open.now" : "open.closed"),
    point.entry_fee_pln > 0 ? t("fee.paid", { fee: point.entry_fee_pln }) : null,
  ].filter(Boolean).join(" · ");
  document.title = `${point.name} · Kropka`;

  if (lastAction) {
    $("done-dot").innerHTML = dotSvg(point.status, { size: 56 });
    $("done-text").textContent = t(`done.${lastAction}`);
  }
}

function showMessage(code) {
  const box = $("message");
  box.textContent = t(`error.${code}`) === `error.${code}` ? t("error.generic") : t(`error.${code}`);
  box.hidden = false;
}

async function onAction(e) {
  const button = e.target.closest("button[data-type]");
  if (!button) return;
  const buttons = document.querySelectorAll(".action");
  buttons.forEach((b) => { b.disabled = true; });
  $("message").hidden = true;
  try {
    const result = await postEvent(pointId, button.dataset.type);
    point = result.point;
    lastAction = result.type;
    $("actions").hidden = true;
    $("done").hidden = false;
    render();
    $("done").focus?.();
  } catch (err) {
    showMessage(err.code);
  } finally {
    buttons.forEach((b) => { b.disabled = false; });
  }
}

async function main() {
  renderLangSwitch($("lang-switch"));
  await initI18n();
  $("brand-dot").innerHTML = dotSvg("ok", { size: 28 });
  document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = dotSvg(el.dataset.icon, { size: 40 }); });
  $("open-map").href = `/?p=${encodeURIComponent(pointId)}`;
  document.querySelector(".action-buttons").addEventListener("click", onAction);
  document.addEventListener("langchange", render);

  try {
    point = await getPoint(pointId);
    $("actions").hidden = false;
    render();
    if (point.offline) {  // cached copy from the service worker: tapping will not work right now
      const box = $("message");
      box.textContent = t("offline.point");
      box.hidden = false;
    }
  } catch (err) {
    $("loading").hidden = true;
    showMessage(err.code);
  }
}

main();
