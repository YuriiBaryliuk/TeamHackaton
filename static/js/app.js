// Main map page: Leaflet map, dot markers, bottom sheet, the Urgent flow.
// Points are refreshed every few seconds while the page is visible, so a tap on a
// QR sticker shows up on the big screen during the demo.
import { getPoints, postUrgent } from "./api.js";
import "./pwa.js";
import { dotSvg } from "./dot.js";
import { getLang, initI18n, LANGS, setLang, t, timeAgo } from "./i18n.js";
import { isWatched, setWatched } from "./watch.js";

const CITY = "krakow";
const KRAKOW_CENTER = [50.0614, 19.9383];
const START_ZOOM = 13;
const REFRESH_MS = 8000;               // spec: 5-10 s for the live demo
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

let map;
let points = new Map();                // id -> point from the API
const markers = new Map();             // id -> Leaflet marker
let sheetMode = null;                  // {kind: "point", id} | {kind: "urgent", result}
let urgentLayer = null;                // user position + line to the result
let hasDemoData = false;
let wasOffline = false;

// "14:05" in the user's language and Warsaw time.
const clockTime = (iso) => new Date(iso).toLocaleTimeString(getLang(),
  { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });

// ---------- helpers ----------

const isBox = (p) => p.has_products || p.status !== "unknown";

function statusWords(p) {
  if (p.status === "unknown" && !p.has_products && p.confidence === "none") return t("status.no_products");
  return t(`status.${p.status}`);
}

function confirmedText(p) {
  if (!p.last_confirmed_at) return t("point.never");
  const faded = p.confidence === "faded" ? ` · ${t("freshness.faded")}` : "";
  return t("point.confirmed", { ago: timeAgo(p.minutes_since_confirmed) }) + faded;
}

// Today's opening hours in Warsaw time, e.g. "Dziś 08:00–20:00".
function hoursToday(hours) {
  if (hours.always) return t("hours.always");
  const weekday = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "Europe/Warsaw" })
    .format(new Date()).toLowerCase().slice(0, 3);
  const today = DAYS.includes(weekday) ? hours[weekday] : null;
  return today ? t("hours.today", { from: today[0], to: today[1] }) : t("hours.closed_today");
}

const prefersApple = () => /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent);

// Route links to a place when we do not know the user's position (the map sheet).
function routesTo(p) {
  return {
    apple: `https://maps.apple.com/?daddr=${p.lat},${p.lon}&dirflg=w`,
    google: `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lon}&travelmode=walking`,
    osm: `https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route=%3B${p.lat}%2C${p.lon}`,
  };
}

function routeButtons(routes) {
  const main = prefersApple() ? routes.apple : routes.google;
  return `<div class="sheet-actions">
      <a class="btn" href="${esc(main)}" target="_blank" rel="noopener">${esc(t("sheet.route"))}</a>
      <a class="btn secondary" href="${esc(routes.osm)}" target="_blank" rel="noopener">OpenStreetMap</a>
    </div>`;
}

function showNotice(text, ms = 6000) {
  const n = $("notice");
  n.textContent = text;
  n.hidden = false;
  clearTimeout(showNotice.timer);
  if (ms) showNotice.timer = setTimeout(() => { n.hidden = true; }, ms);
}

// Honest map: say in the attribution line when demo data is shown.
function setDemoAttribution() {
  map?.attributionControl.setPrefix(hasDemoData ? esc(t("map.demo_attrib")) : "");
}

// ---------- markers ----------

function markerIcon(p) {
  const size = isBox(p) ? 26 : 14;     // boxes are big dots, places without a box small ones
  return L.divIcon({
    className: "kropka-marker",
    html: dotSvg(p.status, { size, faded: p.confidence === "faded" }),
    iconSize: [size + 12, size + 12], // a little extra around the dot makes tapping easier
  });
}

function markerTitle(p) {
  return `${p.name}: ${statusWords(p)}`;
}

function updateMarkers() {
  for (const p of points.values()) {
    const key = `${p.status}|${p.confidence}|${isBox(p)}`;
    let m = markers.get(p.id);
    if (!m) {
      m = L.marker([p.lat, p.lon], { icon: markerIcon(p), title: markerTitle(p), alt: markerTitle(p), keyboard: true,
                                     zIndexOffset: isBox(p) ? 1000 : 0 });
      m.on("click", () => openPoint(p.id));
      m.addTo(map);
      markers.set(p.id, m);
    } else if (m.options.key !== key) {
      m.setIcon(markerIcon(p));       // status changed: swap the dot shape
    }
    m.options.key = key;
    m.getElement()?.setAttribute("title", markerTitle(p));
  }
  for (const [id, m] of markers) {
    if (!points.has(id)) { m.remove(); markers.delete(id); }
  }
}

async function refresh() {
  try {
    const data = await getPoints(CITY);
    points = new Map(data.points.map((p) => [p.id, p]));
    updateMarkers();
    hasDemoData = data.has_demo_data;
    setDemoAttribution();
    // The service worker marks cached data with offline: true (see sw.js).
    if (data.offline) {
      showNotice(t("offline.notice", { time: clockTime(data.generated_at) }), 0);
      wasOffline = true;
    } else if (wasOffline) {
      $("notice").hidden = true;
      wasOffline = false;
    }
    if (sheetMode?.kind === "point") renderPointSheet(); // keep the open sheet live too
  } catch (err) {
    if (err.code === "network") showNotice(t("error.network"));
  }
}

// ---------- bottom sheet ----------

function openSheet(html) {
  $("sheet-body").innerHTML = html;
  $("sheet").hidden = false;
  $("urgent-btn").hidden = true;
}

function closeSheet() {
  $("sheet").hidden = true;
  $("urgent-btn").hidden = false;
  sheetMode = null;
  if (urgentLayer) { urgentLayer.remove(); urgentLayer = null; }
  $("urgent-btn").focus();
}

function pointSheetHtml(p) {
  const what = isBox(p) && p.has_products ? t("sheet.products") : t(`kind.${p.kind}`);
  const facts = [
    `<li>${esc(what)}</li>`,
    `<li>${esc(hoursToday(p.opening_hours))} · ${esc(t(p.open_now ? "open.now" : "open.closed"))}</li>`,
    `<li>${esc(p.entry_fee_pln > 0 ? t("fee.paid", { fee: p.entry_fee_pln }) : t("fee.free"))}</li>`,
    `<li>${esc(t(`access.${p.access}`))}</li>`,
    p.wheelchair ? `<li>${esc(t("sheet.wheelchair"))}</li>` : "",
  ].join("");
  return `
    ${p.is_demo ? `<span class="badge">${esc(t("point.demo"))}</span>` : ""}
    ${p.approved !== false ? "" : `<span class="badge">${esc(t("point.pending"))}</span>`}
    <h2 id="sheet-title" tabindex="-1">${esc(p.name)}</h2>
    ${p.address ? `<p class="muted address">${esc(p.address)}</p>` : ""}
    <div class="status-row">
      ${dotSvg(p.status, { size: 40, faded: p.confidence === "faded" })}
      <div><p class="status-text">${esc(statusWords(p))}</p><p class="muted">${esc(confirmedText(p))}</p></div>
    </div>
    <ul class="facts">${facts}</ul>
    ${routeButtons(routesTo(p))}
    ${p.has_products ? `
    <div class="sheet-links">
      <button class="link-btn" type="button" data-watch="${esc(p.id)}" aria-pressed="${isWatched(p.id)}">
        ${esc(t(isWatched(p.id) ? "watch.on" : "watch.cta"))}</button>
      <a class="link-btn" href="/partner/${encodeURIComponent(p.id)}">${esc(t("partner.link"))}</a>
    </div>` : ""}`;
}

function renderPointSheet() {
  const p = points.get(sheetMode.id);
  if (p) openSheet(pointSheetHtml(p));
}

function openPoint(id) {
  if (urgentLayer) { urgentLayer.remove(); urgentLayer = null; }
  sheetMode = { kind: "point", id };
  renderPointSheet();
  $("sheet-title")?.focus();
}

// ---------- Urgent ----------

function placeCard(place, { primary = false } = {}) {
  const closed = place.open_now ? "" : ` · ${esc(t("open.closed"))}`;
  const fee = place.entry_fee_pln > 0 ? ` · ${esc(t("fee.paid", { fee: place.entry_fee_pln }))}` : "";
  return `
    <div class="place ${primary ? "primary" : ""}">
      <div class="status-row">
        ${dotSvg(place.status, { size: primary ? 40 : 28 })}
        <div>
          <p class="place-name">${esc(place.name)}</p>
          <p class="muted">${esc(t("urgent.walk", { min: Math.max(1, Math.round(place.walking_min)) }))}${fee}${closed}</p>
          ${place.minutes_since_confirmed != null && place.status !== "unknown"
            ? `<p class="muted small">${esc(t("point.confirmed", { ago: timeAgo(place.minutes_since_confirmed) }))}</p>` : ""}
        </div>
      </div>
      ${primary ? routeButtons(place.routes) : ""}
    </div>`;
}

function urgentHtml(r) {
  const parts = [];
  if (r.found) {
    parts.push(`<h2 id="sheet-title" tabindex="-1">${esc(t("urgent.found_title"))}</h2>`, placeCard(r.best, { primary: true }));
    if (r.alternatives.length) {
      parts.push(`<h3>${esc(t("urgent.alternatives"))}</h3>`, ...r.alternatives.map((a) => placeCard(a)));
    }
  } else {
    parts.push(`<h2 id="sheet-title" tabindex="-1">${esc(t("urgent.none_title"))}</h2>`);
    if (r.fallback) parts.push(`<p>${esc(t("urgent.none_text"))}</p>`, placeCard(r.fallback, { primary: true }));
    if (r.best) parts.push(`<h3>${esc(t("urgent.farther"))}</h3>`, placeCard(r.best));
  }
  if (r.night) parts.push(`<p class="muted small">${esc(t("urgent.night"))}</p>`);
  return parts.join("");
}

function drawUrgent(lat, lon, target) {
  if (urgentLayer) urgentLayer.remove();
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  urgentLayer = L.layerGroup([
    // "You are here": solid dark dot with a white border, so it never looks like an "empty" ring.
    L.circleMarker([lat, lon], { radius: 8, color: "#FFFFFF", weight: 3, fillColor: "#2B1D22", fillOpacity: 1 }),
  ]);
  const coords = target ? [[lat, lon], [target.lat, target.lon]] : [[lat, lon]];
  if (target) {
    urgentLayer.addLayer(L.polyline(coords, { color: accent, weight: 4, dashArray: "6 8", opacity: 0.9 }));
  }
  urgentLayer.addTo(map);
  map.fitBounds(L.latLngBounds(coords), { ...visibleMapPadding(), maxZoom: 16 });
}

// Keep the user and the target in the part of the map NOT covered by the sheet:
// below it on phones (sheet at the bottom), to its right on wide screens.
function visibleMapPadding() {
  const sheet = $("sheet");
  if (sheet.hidden) return { padding: [48, 48] };
  if (window.innerWidth >= 700) return { paddingTopLeft: [sheet.offsetWidth + 64, 48], paddingBottomRight: [48, 48] };
  return { paddingTopLeft: [40, 40], paddingBottomRight: [40, sheet.offsetHeight + 24] };
}

async function runUrgent(lat, lon) {
  try {
    const r = await postUrgent(lat, lon);
    sheetMode = { kind: "urgent", result: r };
    openSheet(urgentHtml(r));
    drawUrgent(lat, lon, r.found ? r.best : r.fallback || r.best);
    $("sheet-title")?.focus();
  } catch (err) {
    showNotice(t(`error.${err.code}`) === `error.${err.code}` ? t("error.generic") : t(`error.${err.code}`));
  }
}

// The browser's own timeout only starts after the permission prompt is answered,
// so we add an overall limit: a person who ignores the prompt is not left waiting.
const GEO_TIMEOUT_MS = 12000;

function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("unsupported"));
    const timer = setTimeout(() => reject(new Error("timeout")), GEO_TIMEOUT_MS);
    navigator.geolocation.getCurrentPosition(
      (pos) => { clearTimeout(timer); resolve(pos); },
      (err) => { clearTimeout(timer); reject(err); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });
}

async function onUrgent() {
  const btn = $("urgent-btn");
  btn.disabled = true;
  $("urgent-label").textContent = t("urgent.searching");
  try {
    const pos = await getPosition();
    await runUrgent(pos.coords.latitude, pos.coords.longitude);
  } catch {
    // No location (denied, no GPS, plain HTTP): offer the map centre instead.
    sheetMode = { kind: "nogeo" };
    openSheet(`
      <h2 id="sheet-title" tabindex="-1">${esc(t("urgent.no_geo_title"))}</h2>
      <p>${esc(t("urgent.no_geo"))}</p>
      <div class="sheet-actions"><button class="btn" id="use-center" type="button">${esc(t("urgent.use_center"))}</button></div>`);
    $("use-center").addEventListener("click", () => {
      const c = map.getCenter();
      runUrgent(c.lat, c.lng);
    });
    $("sheet-title")?.focus();
  } finally {
    btn.disabled = false;
    $("urgent-label").textContent = t("urgent.button");
  }
}

// ---------- header controls ----------

function setupHeader() {
  $("brand-dot").innerHTML = dotSvg("ok", { size: 26 });
  $("urgent-dot").innerHTML = dotSvg("ok", { size: 22 });

  const langSelect = $("lang-select");
  langSelect.innerHTML = LANGS.map((l) => `<option value="${l}">${l.toUpperCase()}</option>`).join("");
  langSelect.addEventListener("change", () => setLang(langSelect.value));

  document.addEventListener("langchange", () => {
    langSelect.value = getLang();
    document.querySelectorAll("#city-select option[data-soon]").forEach((o) => {
      o.textContent = t("city.soon", { city: o.dataset.soon });
    });
    document.querySelectorAll("#legend [data-icon]").forEach((el) => {
      el.innerHTML = dotSvg(el.dataset.icon, { size: el.dataset.small ? 14 : 22, faded: !!el.dataset.faded });
    });
    // Re-render translated dynamic content.
    for (const [id, m] of markers) {
      const p = points.get(id);
      if (p) m.getElement()?.setAttribute("title", markerTitle(p));
    }
    if (sheetMode?.kind === "point") renderPointSheet();
    if (sheetMode?.kind === "urgent") openSheet(urgentHtml(sheetMode.result));
    setDemoAttribution();
  });
}

// ---------- start ----------

async function main() {
  setupHeader();
  await initI18n();

  map = L.map("map", { zoomControl: false, attributionControl: true }).setView(KRAKOW_CENTER, START_ZOOM);
  L.control.zoom({ position: "topright" }).addTo(map); // top-left is the legend
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    crossOrigin: true, // CORS tiles can be cached by the service worker cheaply
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  $("urgent-btn").addEventListener("click", onUrgent);
  $("sheet-close").addEventListener("click", closeSheet);
  // "Look after this point": saved in this browser only (watch.js), listed on /steward.
  $("sheet-body").addEventListener("click", (e) => {
    const id = e.target.closest("[data-watch]")?.dataset.watch;
    if (!id) return;
    setWatched(id, !isWatched(id));
    renderPointSheet();
    if (isWatched(id)) showNotice(t("watch.added"));
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });

  await refresh();

  // /?p=krk-0001 opens that point (used by the "Open the map" link on the QR page).
  const wanted = new URLSearchParams(location.search).get("p");
  if (wanted && points.has(wanted)) {
    const p = points.get(wanted);
    map.setView([p.lat, p.lon], 16);
    openPoint(wanted);
  }

  setInterval(() => { if (document.visibilityState === "visible") refresh(); }, REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
}

main();
