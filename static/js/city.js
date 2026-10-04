// City dashboard: key figures, white spots, demand, fastest-emptying boxes.
// All numbers come ready-made from /api/city/stats (computed in app/stats.py).
import { fillCitySelect, getCity, loadCities, saveCity, savedCity } from "./cities.js";
import { dotSvg } from "./dot.js";
import "./pwa.js";
import { fmtHours, fmtNumber, getLang, initI18n, LANGS, setLang, t, tn } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const TABLE_ROWS = 10;

let stats = null;
let city = "krakow";
let wsMap, demandMap, wsLayer, demandLayer;

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Circle radius from a value: area grows with the value (sqrt), so big numbers do not explode.
const radius = (value, max) => 6 + 22 * Math.sqrt(value / Math.max(1, max));

function makeMap(id) {
  const c = getCity(city);
  const m = L.map(id, { scrollWheelZoom: false }).setView([c.lat, c.lon], 12);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    crossOrigin: true, // CORS tiles can be cached by the service worker cheaply
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(m);
  return m;
}

function renderKpis(k) {
  $("kpi-active").textContent = t("kpi.active_value", { a: fmtNumber(k.active_boxes), b: fmtNumber(k.boxes) });
  $("kpi-fresh").textContent = fmtNumber(k.fresh_pct / 100, { style: "percent" });
  $("kpi-takes").textContent = fmtNumber(k.takes);
  $("kpi-wait").textContent = fmtHours(k.median_empty_to_refill_h);
}

function renderWhiteSpots() {
  const { kpis, white_spots: spots, boxes } = stats;
  $("ws-story").textContent = t("ws.story", {
    n: fmtNumber(kpis.searches_not_found), total: fmtNumber(kpis.searches),
  });

  wsLayer?.remove();
  wsLayer = L.layerGroup().addTo(wsMap);
  const accent = css("--accent");
  const max = Math.max(1, ...spots.map((s) => s.count));
  // Existing boxes as small status dots, so you can see "searches here, no box here".
  for (const b of boxes) {
    L.marker([b.lat, b.lon], {
      icon: L.divIcon({ className: "kropka-marker", html: dotSvg(b.status, { size: 12, faded: b.confidence === "faded" }), iconSize: [12, 12] }),
      keyboard: false, interactive: false,
    }).addTo(wsLayer);
  }
  // White spots: empty rings (the app's "nothing here" shape), bigger = more failed searches.
  for (const s of spots) {
    L.circleMarker([s.lat, s.lon], {
      radius: radius(s.count, max), color: accent, weight: 3, fillColor: accent, fillOpacity: 0.12,
    })
      .bindTooltip(`${esc(tn("n.failed", s.count))} / ${esc(fmtNumber(s.searches))}<br>${esc(t("ws.near", { near: s.near }))}`)
      .addTo(wsLayer);
  }
  if (spots.length) wsMap.fitBounds(L.latLngBounds(spots.map((s) => [s.lat, s.lon])).pad(0.15), { maxZoom: 14 });

  $("ws-list").innerHTML = spots.slice(0, 3).map((s) => `
    <li><strong>${esc(t("ws.near", { near: s.near }))}</strong>
        <span class="muted">${esc(tn("n.failed", s.count))}</span></li>`).join("");
}

function renderDemand() {
  const boxes = stats.boxes.filter((b) => b.takes > 0);
  demandLayer?.remove();
  demandLayer = L.layerGroup().addTo(demandMap);
  const accent = css("--accent");
  const max = Math.max(1, ...boxes.map((b) => b.takes));
  // Biggest first, so small circles are drawn on top and stay hoverable.
  for (const b of [...boxes].sort((a, c) => c.takes - a.takes)) {
    L.circleMarker([b.lat, b.lon], {
      radius: radius(b.takes, max), color: css("--surface"), weight: 2, fillColor: accent, fillOpacity: 0.6,
    })
      .bindTooltip(`${esc(b.name)}<br>${esc(tn("n.takes", b.takes))}`)
      .addTo(demandLayer);
  }
  if (boxes.length) demandMap.fitBounds(L.latLngBounds(boxes.map((b) => [b.lat, b.lon])).pad(0.1), { maxZoom: 14 });
}

function renderTable() {
  const rows = stats.boxes.slice(0, TABLE_ROWS);
  $("table-body").innerHTML = rows.map((b) => `
    <tr>
      <th scope="row">${esc(b.name)}${b.is_demo ? ` <span class="badge">demo</span>` : ""}</th>
      <td class="num">${esc(fmtHours(b.avg_refill_to_empty_h))}</td>
      <td class="num">${esc(fmtHours(b.avg_empty_to_refill_h))}</td>
      <td class="num">${esc(fmtNumber(b.takes))}</td>
      <td class="num">${esc(fmtNumber(b.cycles))}</td>
      <td class="status-cell">${dotSvg(b.status, { size: 16, faded: b.confidence === "faded" })} ${esc(t(`status.${b.status}`))}</td>
    </tr>`).join("");
}

function render() {
  if (!stats) return;
  $("title").textContent = t("dash.title", { city: getCity(stats.city).name });
  $("subtitle").textContent = t("dash.subtitle", { days: stats.days });
  $("demo-footer").hidden = !stats.has_demo_data;
  renderKpis(stats.kpis);
  renderWhiteSpots();
  renderDemand();
  renderTable();
}

async function load() {
  const days = $("days").value;
  $("csv-link").href = `/api/city/stats.csv?city=${encodeURIComponent(city)}&days=${days}`;
  try {
    const res = await fetch(`/api/city/stats?city=${encodeURIComponent(city)}&days=${days}`);
    if (!res.ok) throw new Error(String(res.status));
    stats = await res.json();
  } catch {
    $("subtitle").textContent = t("error.network");
    return;
  }
  render();
  if (stats.offline) {  // cached copy from the service worker
    const time = new Date(stats.generated_at).toLocaleTimeString(getLang(),
      { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });
    $("subtitle").textContent += ` ${t("offline.notice", { time })}`;
  }
}

async function main() {
  $("brand-dot").innerHTML = dotSvg("ok", { size: 26 });
  const langSelect = $("lang-select");
  langSelect.innerHTML = LANGS.map((l) => `<option value="${l}">${l.toUpperCase()}</option>`).join("");
  langSelect.addEventListener("change", () => setLang(langSelect.value));
  document.addEventListener("langchange", () => {
    langSelect.value = getLang();
    document.querySelectorAll("#days option").forEach((o) => { o.textContent = t("dash.days", { n: o.value }); });
    render();
  });
  await Promise.all([initI18n(), loadCities()]);
  city = savedCity();
  fillCitySelect($("city-select"), city);
  $("city-select").addEventListener("change", (e) => {
    city = e.target.value;
    saveCity(city);
    const c = getCity(city);
    wsMap.setView([c.lat, c.lon], 12);       // load() then fits the maps to the data
    demandMap.setView([c.lat, c.lon], 12);
    load();
  });

  wsMap = makeMap("ws-map");
  demandMap = makeMap("demand-map");
  $("days").addEventListener("change", load);
  await load();
}

main();
