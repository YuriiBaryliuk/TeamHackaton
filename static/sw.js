// Kropka service worker. Served at /sw.js so it controls the whole site.
//
// Strategies (simple and explainable):
//   pages (navigations)   network first, cached copy when offline
//   static files, Leaflet stale-while-revalidate: instant from cache, refreshed in the background
//   GET /api/*            network first; the last good response is kept and returned offline
//                         with "offline": true added, so the page can say "data from HH:MM"
//   map tiles             cache first, at most MAX_TILES kept
//   POST (marks, Urgent)  never cached, always the network
//
// Bump VERSION when the app shell changes: old caches are deleted on activate.

const VERSION = "kropka-v9";
const SHELL = `${VERSION}-shell`;
const API = `${VERSION}-api`;
const TILES = "kropka-tiles";
const MAX_TILES = 300;

const LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
const LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";

const SHELL_FILES = [
  "/",
  "/city",
  "/add",
  "/steward",
  "/static/point.html",
  "/static/partner.html",
  "/static/css/styles.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/city.js",
  "/static/js/dot.js",
  "/static/js/i18n.js",
  "/static/js/point.js",
  "/static/js/pwa.js",
  "/static/js/add.js",
  "/static/js/steward.js",
  "/static/js/partner.js",
  "/static/js/watch.js",
  "/static/js/header.js",
  "/static/js/cities.js",
  "/static/i18n/pl.json",
  "/static/i18n/en.json",
  "/static/i18n/uk.json",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/favicon.svg",
  "/static/fonts/nunito-latin.woff2",
  "/static/fonts/nunito-latin-ext.woff2",
  "/static/fonts/nunito-cyrillic.woff2",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    await cache.addAll(SHELL_FILES);
    // CDN files are cross-origin: fetch them in CORS mode so the integrity check still works.
    await cache.addAll([LEAFLET_CSS, LEAFLET_JS].map((url) => new Request(url, { mode: "cors" })));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keep = [SHELL, API, TILES];
    for (const name of await caches.keys()) {
      if (!keep.includes(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;                       // marks and Urgent go straight to the network
  const url = new URL(req.url);

  if (url.origin === location.origin && url.pathname.startsWith("/api/")) {
    if (url.pathname.endsWith(".csv")) return;
    event.respondWith(apiNetworkFirst(req));
  } else if (req.mode === "navigate") {
    event.respondWith(pageNetworkFirst(req, url));
  } else if (url.hostname === "tile.openstreetmap.org") {
    event.respondWith(tileCacheFirst(req));
  } else if (url.origin === location.origin || url.hostname.endsWith("cdnjs.cloudflare.com")) {
    event.respondWith(staleWhileRevalidate(req));
  }
});

async function pageNetworkFirst(req, url) {
  const cache = await caches.open(SHELL);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    // /p/<id> pages all share the same HTML; its JS loads the point (from the API cache).
    const fallback = url.pathname.startsWith("/p/") ? "/static/point.html"
      : url.pathname.startsWith("/partner/") ? "/static/partner.html" : "/";
    return (await cache.match(req)) || (await cache.match(fallback)) || Response.error();
  }
}

async function apiNetworkFirst(req) {
  const cache = await caches.open(API);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    const cached = await cache.match(req);
    let data = cached ? await cached.json() : null;
    // A single point never opened before: take it from the cached list of all points.
    const single = new URL(req.url).pathname.match(/^\/api\/points\/([^/]+)$/);
    if (!data && single) {
      const id = decodeURIComponent(single[1]);
      for (const key of await cache.keys()) {   // any cached city list may contain it
        if (!new URL(key.url).pathname.endsWith("/api/points")) continue;
        data = (await (await cache.match(key)).json()).points.find((p) => p.id === id) || null;
        if (data) break;
      }
    }
    if (!data) return Response.error();
    return new Response(JSON.stringify({ ...data, offline: true }), {
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(SHELL);
  const cached = await cache.match(req);
  const fresh = fetch(req)
    .then((res) => { if (res.ok) cache.put(req, res.clone()); return res; })
    .catch(() => cached || Response.error());
  return cached || fresh;
}

async function tileCacheFirst(req) {
  const cache = await caches.open(TILES);
  const cached = await cache.match(req);
  if (cached) return cached;
  try {
    const res = await fetch(req);
    if (res.ok) {
      await cache.put(req, res.clone());
      const keys = await cache.keys();
      for (const old of keys.slice(0, Math.max(0, keys.length - MAX_TILES))) await cache.delete(old);
    }
    return res;
  } catch {
    return Response.error();
  }
}
