"""Kropka FastAPI application: routes and the static file mount.

Routes stay thin: they read input, call the logic in status.py / urgent.py /
abuse.py, and return a pydantic model. /docs is generated from these.
"""
import csv
import io
import json
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import abuse, db, points
from app.schemas import (CityStats, ErrorResponse, EventIn, EventOut, NewPointIn, NewPointOut, Point,
                         PointList, PointStats, UrgentIn, UrgentOut)
from app.stats import load_point_stats, load_stats
from app.status import compute_status, points_with_status
from app.urgent import CITY_CENTRES, LOG_RADIUS_M, find_urgent, haversine_m, is_open, log_urgent_search

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# Slim Linux images do not know .woff2; tell StaticFiles the proper font type.
mimetypes.add_type("font/woff2", ".woff2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_db(conn)  # creates tables on first start, no-op afterwards
    conn.close()
    if "DEVICE_SALT" not in os.environ:
        logging.getLogger("uvicorn.error").warning(
            "DEVICE_SALT is not set: using the development salt. Set it in production.")
    yield


app = FastAPI(
    title="Kropka API",
    description="Live map of free menstrual hygiene products in Kraków. "
    "No accounts, no personal data. Errors return `{detail: {code, message}}`; "
    "`code` is stable and translated by the frontend.",
    version="0.1.0",
    lifespan=lifespan,
)


def get_db():
    """One short-lived SQLite connection per request, closed afterwards."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def error(status: int, code: str, message: str, retry_after_s: int | None = None) -> HTTPException:
    headers = {"Retry-After": str(retry_after_s)} if retry_after_s else None
    return HTTPException(status, {"code": code, "message": message, "retry_after_s": retry_after_s}, headers=headers)


def device_hash_for(request: Request, response: Response) -> str:
    """Anonymous device id: reuse the cookie, or give this browser a new one. Returns its salted hash."""
    device_id = request.cookies.get(abuse.DEVICE_COOKIE)
    if not abuse.is_valid_device_id(device_id):
        device_id = abuse.new_device_id()
    response.set_cookie(
        abuse.DEVICE_COOKIE, device_id, max_age=abuse.COOKIE_MAX_AGE_S,
        httponly=True, samesite="lax", secure=request.url.scheme == "https",
    )
    return abuse.hash_device(device_id)


def with_display_fields(point: dict, now) -> dict:
    """Parse the opening hours JSON and add the 'open now' flag."""
    point["opening_hours"] = json.loads(point["opening_hours"])
    point["open_now"] = is_open(point["opening_hours"], now)
    return point


def load_points(conn, city: str, now) -> list[dict]:
    """All points of a city with their computed status."""
    rows = points_with_status(db.fetch_points(conn, city), db.fetch_events_by_point(conn, city), now)
    return [with_display_fields(p, now) for p in rows]


def load_point(conn, point_id: str, now) -> dict:
    point = db.fetch_point(conn, point_id)
    if point is None:
        raise error(404, "point_not_found", "This point does not exist.")
    return with_display_fields({**point, **compute_status(db.fetch_events(conn, point_id), now)}, now)


# ---------- meta ----------

class Health(BaseModel):
    status: str
    app: str


@app.get("/api/health", response_model=Health, tags=["meta"])
def health() -> Health:
    """Simple liveness check, used by the hosting platform and by us."""
    return Health(status="ok", app="kropka")


# ---------- points ----------

@app.get("/api/points", response_model=PointList, tags=["points"])
def list_points(city: str = "krakow", conn=Depends(get_db)) -> PointList:
    """All points of a city with live status, freshness and minutes since the last confirmation."""
    now = db.utc_now()
    rows = load_points(conn, city, now)
    return PointList(
        city=city,
        generated_at=db.to_iso(now),
        has_demo_data=any(p["is_demo"] for p in rows),
        points=rows,
    )


@app.get("/api/points/{point_id}", response_model=Point, tags=["points"],
         responses={404: {"model": ErrorResponse}})
def get_point(point_id: str, conn=Depends(get_db)) -> Point:
    """One point in full detail. Used by the QR landing page /p/{id}."""
    return load_point(conn, point_id, db.utc_now())


@app.post("/api/points/{point_id}/events", response_model=EventOut, tags=["points"],
          responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                     404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
def post_event(point_id: str, body: EventIn, request: Request, response: Response,
               conn=Depends(get_db)) -> EventOut:
    """Record "took", "empty" or "refilled" for a point and return its new status.

    Rate limits: one event of the same type per point per device per 10 minutes,
    30 events per device per day (HTTP 429). Source 'geo' must be within 150 m.
    """
    now = db.utc_now()
    point = db.fetch_point(conn, point_id)
    if point is None:
        raise error(404, "point_not_found", "This point does not exist.")
    device_hash = device_hash_for(request, response)

    if body.source == "geo":
        problem = abuse.check_geo(point, body.lat, body.lon)
        if problem:
            raise error(400 if problem["code"] == "location_required" else 403, **problem)

    problem = abuse.check_rate_limit(conn, device_hash, point_id, body.type, now)
    if problem:
        raise error(429, **problem)

    db.insert_event(conn, point_id, body.type, body.source, device_hash, now)  # lat/lon NOT stored
    return EventOut(saved=True, type=body.type, point=load_point(conn, point_id, now))


@app.post("/api/points", response_model=NewPointOut, status_code=201, tags=["points"],
          responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                     429: {"model": ErrorResponse}})
def add_point(body: NewPointIn, request: Request, response: Response, city: str = "krakow",
              conn=Depends(get_db)) -> NewPointOut:
    """Suggest a new box location. It is saved as waiting for review (approved = false):
    shown on the map with a badge, never recommended by Urgent until approved.

    Limits: inside the city, not within 25 m of an existing point (409),
    at most 3 new points per device per day (429). No photos and no personal data.
    """
    now = db.utc_now()
    device_hash = device_hash_for(request, response)
    if not points.inside_city(city, body.lat, body.lon):
        raise error(422, "outside_city", "This location is outside the city.")
    try:
        hours = points.build_opening_hours(body.hours, body.open_from, body.open_to)
    except ValueError:
        raise error(422, "bad_hours", "Opening time must be before closing time.")
    existing = points.nearby_point(conn, body.lat, body.lon)
    if existing:
        raise HTTPException(409, {"code": "duplicate", "message": "There is already a point here.",
                                  "point_id": existing})
    if points.added_today(conn, device_hash, now) >= points.MAX_NEW_POINTS_PER_DAY:
        raise error(429, "add_limit", "Thank you! You can add more points tomorrow.")
    point_id = points.insert_point(conn, body.model_dump(), hours, device_hash, now, city)
    return NewPointOut(id=point_id, point=load_point(conn, point_id, now))


@app.get("/api/points/{point_id}/stats", response_model=PointStats, tags=["points"],
         responses={404: {"model": ErrorResponse}})
def point_stats(point_id: str, days: int = Query(30, ge=1, le=365), conn=Depends(get_db)) -> PointStats:
    """How a single box was used in the last `days` days (for the partner page)."""
    if db.fetch_point(conn, point_id) is None:
        raise error(404, "point_not_found", "This point does not exist.")
    return load_point_stats(conn, point_id, days)


# ---------- urgent ----------

@app.post("/api/urgent", response_model=UrgentOut, tags=["urgent"])
def urgent(body: UrgentIn, city: str = "krakow", conn=Depends(get_db)) -> UrgentOut:
    """Nearest point that is in stock, freshly confirmed and open now, plus 2 alternatives.

    If nothing is within 10 minutes' walk, `found` is false and `fallback` is the
    nearest pharmacy or shop. The search is logged anonymously (coordinates
    rounded to ~100 m) for the white-spots map.
    """
    now = db.utc_now()
    result = find_urgent(load_points(conn, city, now), body.lat, body.lon, now)
    centre = CITY_CENTRES.get(city)
    if centre and haversine_m(body.lat, body.lon, *centre) <= LOG_RADIUS_M:
        log_urgent_search(conn, body.lat, body.lon, result, now)  # only searches inside the city
    return result


# ---------- city dashboard ----------

CSV_COLUMNS = ["id", "name", "kind", "status", "takes", "empties", "refills", "cycles",
               "avg_refill_to_empty_h", "avg_empty_to_refill_h", "is_demo"]


@app.get("/api/city/stats", response_model=CityStats, tags=["city"])
def city_stats(city: str = "krakow", days: int = Query(30, ge=1, le=365), conn=Depends(get_db)) -> CityStats:
    """Anonymous aggregates for the city dashboard: key figures, white spots
    (Urgent searches that found nothing, on a ~500 m grid) and per-box cycles."""
    return load_stats(conn, city, days, db.utc_now())


@app.get("/api/city/stats.csv", tags=["city"], response_class=PlainTextResponse,
         responses={200: {"content": {"text/csv": {}}}})
def city_stats_csv(city: str = "krakow", days: int = Query(30, ge=1, le=365), conn=Depends(get_db)):
    """The per-box table as CSV (opens in Excel). Contains no personal data."""
    stats = load_stats(conn, city, days, db.utc_now())
    out = io.StringIO()
    out.write("﻿")  # BOM: Excel then reads Polish characters correctly
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(stats["boxes"])
    filename = f"kropka_{city}_{days}d.csv"
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------- pages ----------

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """The main map page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    """Served from the site root so the service worker may control every page.
    no-cache: browsers always check for a new version."""
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "icons" / "favicon.ico", media_type="image/x-icon")


@app.get("/add", include_in_schema=False)
def add_page() -> FileResponse:
    """Suggest a new point."""
    return FileResponse(STATIC_DIR / "add.html")


@app.get("/steward", include_in_schema=False)
def steward_page() -> FileResponse:
    """"My points": boxes this browser looks after (kept in the browser only)."""
    return FileResponse(STATIC_DIR / "steward.html")


@app.get("/partner/{point_id}", include_in_schema=False)
def partner_page(point_id: str, conn=Depends(get_db)):
    """Thank-you page for a partner venue: how often its box was used."""
    if db.fetch_point(conn, point_id) is None:
        return HTMLResponse("<h1>Kropka</h1><p>Nie znaleziono punktu / Point not found.</p>", status_code=404)
    return FileResponse(STATIC_DIR / "partner.html")


@app.get("/city", include_in_schema=False)
def city_page() -> FileResponse:
    """Dashboard for the city, schools and NGOs."""
    return FileResponse(STATIC_DIR / "city.html")


@app.get("/p/{point_id}", include_in_schema=False)
def point_page(point_id: str, conn=Depends(get_db)):
    """The URL printed in the QR code. Serves the landing page; its JS loads the point."""
    if db.fetch_point(conn, point_id) is None:
        return HTMLResponse("<h1>Kropka</h1><p>Nie znaleziono punktu / Point not found.</p>", status_code=404)
    return FileResponse(STATIC_DIR / "point.html")


# All CSS, JS, icons and translations are served from /static/...
# Mounted last so API routes always take priority.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
