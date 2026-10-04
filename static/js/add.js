// "Add a point": pick the place on a small map (or use GPS), fill a short form.
// The server saves it as waiting for review (see app/points.py).
import { postNewPoint } from "./api.js";
import "./pwa.js";
import { dotSvg } from "./dot.js";
import { setupHeader } from "./header.js";
import { initI18n, t } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const KRAKOW_CENTER = [50.0614, 19.9383];
let map, marker;

function initMap() {
  map = L.map("pick-map").setView(KRAKOW_CENTER, 14);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, crossOrigin: true,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  marker = L.marker(KRAKOW_CENTER, {
    draggable: true, keyboard: true,
    icon: L.divIcon({ className: "kropka-marker", html: dotSvg("ok", { size: 30 }), iconSize: [44, 44] }),
  }).addTo(map);
  map.on("click", (e) => marker.setLatLng(e.latlng)); // tap the map to move the dot
}

function useMyLocation() {
  if (!navigator.geolocation) return showMessage(t("urgent.no_geo"));
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const ll = [pos.coords.latitude, pos.coords.longitude];
      marker.setLatLng(ll);
      map.setView(ll, 17);
    },
    () => showMessage(t("add.no_location")),
    { enableHighAccuracy: true, timeout: 10000 },
  );
}

function showMessage(text, html = false) {
  const box = $("message");
  if (html) box.innerHTML = text; else box.textContent = text;
  box.hidden = false;
}

function errorText(err) {
  const key = `error.${err.code}`;
  return t(key) === key ? t("error.generic") : t(key);
}

async function onSubmit(e) {
  e.preventDefault();
  $("message").hidden = true;
  const name = $("name").value.trim();
  if (name.length < 3) {
    $("name").focus();
    return showMessage(t("add.name_required"));
  }
  const { lat, lng } = marker.getLatLng();
  const data = {
    name, lat, lon: lng,
    kind: $("kind").value,
    address: $("address").value.trim() || null,
    access: $("access").value,
    hours: $("hours").value,
    open_from: $("hours").value === "always" ? null : $("open_from").value,
    open_to: $("hours").value === "always" ? null : $("open_to").value,
    wheelchair: $("wheelchair").checked,
  };
  $("submit").disabled = true;
  try {
    const result = await postNewPoint(data);
    $("add-form").hidden = true;
    $("done").hidden = false;
    $("done-dot").innerHTML = dotSvg("unknown", { size: 56 });
    $("done-text").textContent = t("add.done", { id: result.id });
    $("done-map").href = `/?p=${encodeURIComponent(result.id)}`;
    $("done-point").href = `/p/${encodeURIComponent(result.id)}`;
    $("done").focus();
  } catch (err) {
    if (err.code === "duplicate" && err.detail?.point_id) {
      const href = `/?p=${encodeURIComponent(err.detail.point_id)}`;
      showMessage(`${t("error.duplicate")} <a href="${href}">${t("add.see_existing")}</a>`, true);
    } else {
      showMessage(errorText(err));
    }
  } finally {
    $("submit").disabled = false;
  }
}

async function main() {
  setupHeader();
  await initI18n();
  initMap();
  $("locate").addEventListener("click", useMyLocation);
  $("hours").addEventListener("change", () => { $("times").hidden = $("hours").value === "always"; });
  $("add-form").addEventListener("submit", onSubmit);
}

main();
