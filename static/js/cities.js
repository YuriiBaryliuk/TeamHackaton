// The selected city: from ?city=..., else remembered in this browser, else Kraków.
// The list of cities (names and map centres) comes from /api/cities.
const KEY = "kropka_city";
export const DEFAULT_CITY = "krakow";

let cities = [];

export async function loadCities() {
  try {
    const res = await fetch("/api/cities");
    if (res.ok) cities = await res.json();
  } catch { /* offline: the service worker usually has a copy */ }
  if (!cities.length) cities = [{ id: DEFAULT_CITY, name: "Kraków", lat: 50.0614, lon: 19.9383 }];
  return cities;
}

export const getCity = (id) => cities.find((c) => c.id === id) || cities[0];

export function savedCity() {
  const fromUrl = new URLSearchParams(location.search).get("city");
  let stored = null;
  try { stored = localStorage.getItem(KEY); } catch { /* private mode */ }
  const wanted = fromUrl || stored || DEFAULT_CITY;
  return cities.some((c) => c.id === wanted) ? wanted : DEFAULT_CITY;
}

export function saveCity(id) {
  try { localStorage.setItem(KEY, id); } catch { /* private mode */ }
  const url = new URL(location.href);
  url.searchParams.set("city", id);
  history.replaceState(null, "", url);
}

// Fill a <select> with the cities and keep it in sync.
export function fillCitySelect(select, current) {
  select.innerHTML = cities.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  select.value = current;
}
