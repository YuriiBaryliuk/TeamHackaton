// Partner profile /partner/{id}: a thank-you page for the venue hosting a box,
// with how often it was used in the last 30 days.
import { getPoint, getPointStats } from "./api.js";
import "./pwa.js";
import { dotSvg } from "./dot.js";
import { setupHeader } from "./header.js";
import { fmtHours, fmtNumber, initI18n, t, tn } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const DAYS = 30;
const pointId = decodeURIComponent(location.pathname.split("/partner/")[1] || "").replace(/\/$/, "");
let point = null;
let stats = null;

function render() {
  if (!point || !stats) return;
  $("loading").hidden = true;
  $("profile").hidden = false;
  $("demo-badge").hidden = !point.is_demo;
  $("name").textContent = point.name;
  $("address").textContent = point.address || "";
  $("hero-dot").innerHTML = dotSvg("ok", { size: 48 });
  $("uses").textContent = tn("n.uses", stats.takes);
  $("uses-period").textContent = t("partner.period", { days: DAYS });
  $("refills").textContent = fmtNumber(stats.refills);
  $("runs-out").textContent = fmtHours(stats.avg_refill_to_empty_h);
  $("wait").textContent = fmtHours(stats.avg_empty_to_refill_h);
  $("now").innerHTML = `${dotSvg(point.status, { size: 22, faded: point.confidence === "faded" })} ${t(`status.${point.status}`)}`;
  // A friendly tip when the box runs out fast: bigger box or more frequent refills.
  const fast = stats.avg_refill_to_empty_h != null && stats.avg_refill_to_empty_h < 48;
  $("tip").hidden = !fast;
  $("tip").textContent = fast ? t("partner.tip_fast") : "";
  $("qr-link").href = `/p/${encodeURIComponent(point.id)}`;
  $("map-link").href = `/?p=${encodeURIComponent(point.id)}`;
  document.title = `${point.name} · Kropka`;
}

async function main() {
  setupHeader();
  await initI18n();
  document.addEventListener("langchange", render);
  try {
    [point, stats] = await Promise.all([getPoint(pointId), getPointStats(pointId, DAYS)]);
    render();
  } catch (err) {
    console.error(err);
    $("loading").hidden = true;
    const key = `error.${err.code}`;
    $("message").textContent = t(key) === key ? t("error.generic") : t(key);
    $("message").hidden = false;
  }
}

main();
