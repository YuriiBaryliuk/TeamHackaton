# Kropka

A live map of free menstrual hygiene products in Kraków. Built at HackYeah 2026 for the "ImpactHer: Technology for Real Change" task.

A QR sticker on every box opens a page with three buttons: **Took / Empty / Refilled**. An **Urgent** button finds the nearest point that is in stock and open right now. A city dashboard shows demand and the **white spots** where boxes are missing.

> Status: work in progress (milestones M0 to M7 done).

## Pages

| URL | What |
| --- | --- |
| `/` | Map of Kraków with live dots and the Urgent button. Refreshes every 8 s while visible. `/?p=<id>` opens one point. |
| `/p/<id>` | QR landing page with the Took / Empty / Refilled buttons |
| `/city` | City dashboard: key figures, white spots, demand, fastest-emptying boxes, CSV |
| `/docs` | API documentation |

**Geolocation needs HTTPS** (or `localhost`). On a phone over plain HTTP, Urgent falls back to "search from the map centre".

## Seed the database

```bash
python -m scripts.seed_points        # 46 real city toilets + 27 demo points
python -m scripts.seed_demo_events   # 30 days of demo events and Urgent searches
```

Both are safe to run again. The database file is `data/kropka.db`; delete it to start from scratch.

**Real vs demo data**

- **Real:** public toilets from the city's open dataset "ZIW Toalety miejskie". The script downloads them from the city's server and keeps a snapshot in `data/krakow_toilets.geojson` for offline use. Ids are `krk-1001` to `krk-1050`, built from the dataset's own ids.
- **Demo:** 27 hand-made points (`krk-0001` to `krk-0026`, plus `krk-demo` for the stage sticker) and all generated events and searches. Their names and positions are illustrative, and every one of these rows has `is_demo = 1`.

## Core logic

- [app/stats.py](app/stats.py) builds the dashboard numbers. A **white spot** is a grid cell of about 500 m where at least half of the Urgent searches found nothing within a 10-minute walk.

- [app/status.py](app/status.py) decides each point's status (ok, low, empty, unknown) and how fresh it is (fresh, faded, stale).
- [app/urgent.py](app/urgent.py) finds the nearest point that is in stock, freshly confirmed and open now, with a pharmacy or shop fallback.
- Both are pure functions with every threshold as a named constant at the top of the file, and both are covered by tests.

## Run locally

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

- http://127.0.0.1:8000/ for the app
- http://127.0.0.1:8000/docs for the interactive API documentation
- http://127.0.0.1:8000/api/health for a health check

## Test

```bash
pytest
```

## Tech choices

| Layer | Choice |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn |
| Database | SQLite via the standard-library `sqlite3` module. It needs no extra dependency, and the SQL is visible and easy to explain. |
| Frontend | Plain HTML, CSS and vanilla JS, served by FastAPI. No build step. |
| Map | Leaflet with OpenStreetMap tiles |

## Project layout

```
app/       FastAPI app and core logic (status, urgent search, stats)
static/    HTML, CSS, JS, translations, PWA files
scripts/   seeding and QR sticker generation
data/      SQLite database (gitignored) and source data
tests/     pytest tests
```

## QR stickers

```bash
BASE_URL=https://your-public-url python -m scripts.make_qr          # all points with a QR
BASE_URL=https://your-public-url python -m scripts.make_qr krk-demo # just the stage sticker
```

This writes `out/stickers/<id>.png`, a 60 mm round sticker at 300 dpi, plus `out/stickers/sheet.pdf` with 12 stickers per A4 page. The QR codes use error correction level H and a 4-module quiet zone.

**Testing on a phone over Wi-Fi.** The QR page does not need GPS, so plain HTTP on your LAN works:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
BASE_URL=http://$(ipconfig getifaddr en0):8000 python -m scripts.make_qr krk-demo
```

The phone must be on the same Wi-Fi network. Some event Wi-Fi networks block traffic between devices; if so, use a tunnel (`cloudflared`/`ngrok`) or the deployed URL.

## API

Interactive documentation is at `/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/points?city=krakow` | All points with live status and freshness |
| GET | `/api/points/{id}` | One point (used by the QR page) |
| POST | `/api/points/{id}/events` | `{type: took/empty/refilled, source: qr/geo/steward/partner, lat?, lon?}`. Returns the new status. |
| POST | `/api/urgent` | `{lat, lon}`. Returns the best point, alternatives and a fallback. |
| GET | `/api/city/stats?city=krakow&days=30` | Dashboard aggregates |
| GET | `/api/city/stats.csv?days=30` | Per-box table as CSV |
| GET | `/p/{id}` | QR landing page |

Errors look like `{"detail": {"code": "too_soon", "message": "...", "retry_after_s": 600}}`. The `code` is stable, and the frontend translates it.

**Anti-abuse** ([app/abuse.py](app/abuse.py)): each browser gets an anonymous random id in the `kropka_did` cookie. Only a salted hash of it is stored. A device can send one event of the same type per point per 10 minutes and 30 events per day; beyond that the server returns HTTP 429. `geo` events must come from within 150 m of the point, and those coordinates are never stored.

Example:

```bash
curl -c jar -b jar -X POST localhost:8000/api/points/krk-0001/events \
     -H 'content-type: application/json' -d '{"type":"took"}'
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DEVICE_SALT` | Secret salt for hashing device ids. **Set it in production.** |
| `KROPKA_DB` | Path to the SQLite file (default `data/kropka.db`) |

## PWA and offline

- `static/manifest.webmanifest` and icons make the app installable ("Add to home screen"). Regenerate the icons with `python -m scripts.make_icons`.
- `static/sw.js` is served at `/sw.js` so it controls the whole site. Pages are network-first. Static files are served from cache and refreshed in the background. The API is network-first, and the last good response is used offline, so the map shows "offline, data from HH:MM". Marks are never cached.
- **When you change frontend files, bump `VERSION` in `sw.js`**, or the browser may show the old files once. In Chrome DevTools, *Application → Service workers → Update on reload* helps while developing.
- Service workers only run on HTTPS or `localhost`.

## Deploy

TODO (milestone M8).

## Known limitations

TODO.
