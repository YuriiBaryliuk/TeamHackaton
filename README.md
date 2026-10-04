# Kropka

A live map of free menstrual hygiene products in Kraków. Built at HackYeah 2026 for the "ImpactHer: Technology for Real Change" task.

A QR sticker on every box opens a page with three buttons: **Took / Empty / Refilled**. An **Urgent** button finds the nearest point that is in stock and open right now. A city dashboard shows demand and the **white spots** where boxes are missing.

> Status: work in progress (milestones M0 to M9 done).

**Live demo:** https://kropka-05q6.onrender.com · [city dashboard](https://kropka-05q6.onrender.com/city) · [API docs](https://kropka-05q6.onrender.com/docs) · [stage box](https://kropka-05q6.onrender.com/p/krk-demo)

## Pages

| URL | What |
| --- | --- |
| `/` | Map of Kraków with live dots and the Urgent button. Refreshes every 8 s while visible. `/?p=<id>` opens one point. |
| `/p/<id>` | QR landing page with the Took / Empty / Refilled buttons |
| `/city` | City dashboard: key figures, white spots, demand, fastest-emptying boxes, CSV |
| `/add` | Suggest a new point (map picker + short form). Saved as "waiting for review". |
| `/steward` | "My points": boxes this browser looks after, with an in-app alert when one runs empty. `/steward?watch=krk-demo` adds the stage box. |
| `/partner/<id>` | Thank-you page for a venue: how often its box was used in the last 30 days |
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
| POST | `/api/points` | Suggest a new point. Limits: inside the city, nothing within 25 m (409), 3 per device per day (429). |
| GET | `/api/points/{id}/stats?days=30` | Usage of one box (partner page) |
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

## Reviewing suggested points

Points added on `/add` get `approved = 0`. They show on the map with a "waiting for review" badge, and Urgent never recommends them. There is no admin login (no accounts at all); whoever has server access runs:

```bash
python -m scripts.moderate list
python -m scripts.moderate approve krk-2001
python -m scripts.moderate reject krk-2001   # deletes the point and its marks
```

On Render, use the service's **Shell** tab. Photos are deliberately not supported: they could show people and would need moderation.

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

The app ships as one Docker image ([Dockerfile](Dockerfile)). On start, [scripts/bootstrap.py](scripts/bootstrap.py) seeds the database if it is empty: city toilets from the saved snapshot (no network needed), plus demo points and 30 days of demo events ending "now". Then Uvicorn starts with `--proxy-headers`, so the app knows it is behind HTTPS.

### Render (free plan)

1. Push the repository to GitHub, including `Dockerfile` and `render.yaml`.
2. Create an account at https://render.com and choose **Sign in with GitHub**.
3. Go to **New → Blueprint**, pick this repository and click **Apply**. [render.yaml](render.yaml) creates the web service `kropka` in Frankfurt and generates a random `DEVICE_SALT`.
4. Wait for the first build, which takes about 3 to 5 minutes. The app runs at `https://kropka-XXXX.onrender.com`.
5. Print the stickers for that URL on your laptop:

   ```bash
   BASE_URL=https://kropka-XXXX.onrender.com python -m scripts.make_qr krk-demo
   ```

**Free-plan behaviour you need to know:**

- **No persistent disk.** Every restart or redeploy re-creates the database from scratch: same points, fresh demo events. Marks made live are lost on restart. That is fine for the demo; real use needs a paid persistent disk (set `KROPKA_DB` to a path on it) or Postgres.
- **The service sleeps after about 15 minutes without traffic.** The first request after that takes up to a minute. **Open the URL 2 to 3 minutes before going on stage.**
- Every push to `main` redeploys automatically.

### Railway or Fly.io

Both deploy the same `Dockerfile`. Set the `DEVICE_SALT` variable to a long random string. The container reads `PORT` from the platform.

### Run the container locally

```bash
docker build -t kropka .
docker run -p 8000:8000 -e DEVICE_SALT=change-me kropka
```

### Plan B for the demo: tunnel from the laptop

If the venue Wi-Fi or the host fails, a quick tunnel gives the laptop a public HTTPS URL without any account:

```bash
brew install cloudflared
uvicorn app.main:app --port 8000 --proxy-headers --forwarded-allow-ips='*'
cloudflared tunnel --url http://localhost:8000   # prints https://<random>.trycloudflare.com
```

The URL changes every time, so print the stage sticker after starting the tunnel.

### Environment variables

| Variable | Where | Purpose |
| --- | --- | --- |
| `DEVICE_SALT` | server | Secret salt for hashing anonymous device ids. Generated by Render. |
| `KROPKA_DB` | server | SQLite path (default `data/kropka.db`; `/app/data/kropka.db` in Docker) |
| `PORT` | server | Set by the host; defaults to 8000 |
| `BASE_URL` | your laptop | Public URL written into the QR stickers by `make_qr.py` |

## Known limitations

TODO.
