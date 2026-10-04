"""The "Urgent" search: nearest point that is in stock, freshly confirmed and open now.

Pure functions, except log_urgent_search() which writes one row.

Rules:
- Candidates: status ok or low, confidence fresh, approved, open now (Europe/Warsaw time).
- Distance: haversine. Walking minutes = distance * 1.3 (streets are not straight) / 80 m per minute.
- found = True only if the best candidate is within 10 minutes' walk.
- Otherwise we also return a fallback: the nearest open pharmacy or shop,
  where products can be bought. The user is never left with nothing.
- At night (22:00 to 06:00) points open 24/7 are ranked first, because those
  are the places that have people around at night.
"""
import json
import math
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from app.db import to_iso

TZ = ZoneInfo("Europe/Warsaw")
EARTH_RADIUS_M = 6_371_000
DETOUR_FACTOR = 1.3          # real walking routes are ~30% longer than a straight line
WALK_M_PER_MIN = 80          # ~4.8 km/h
MAX_WALK_MIN = 10            # "found" threshold
ALTERNATIVES = 2
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 6
FALLBACK_KINDS = ("pharmacy", "shop")
IN_STOCK = ("ok", "low")
COORD_DECIMALS = 3           # ~100 m: we never store exact user positions

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # index = datetime.weekday()


# ---------- geometry ----------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def walking_minutes(distance_m: float) -> float:
    return distance_m * DETOUR_FACTOR / WALK_M_PER_MIN


# ---------- opening hours ----------
# Format (stored as JSON text in points.opening_hours):
#   {"always": true}                                    open 24/7
#   {"mon": ["08:00", "20:00"], "sat": ["10:00", "14:00"]}  a missing day = closed
#   ["18:00", "02:00"]  closes after midnight (the early hours belong to the day before)
#   "24:00" is allowed as a closing time.
#   {"unknown": true}                                   hours not known: never counted as open

def parse_opening_hours(value: str | dict) -> dict:
    return json.loads(value) if isinstance(value, str) else value


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def is_open(opening_hours: str | dict, now: datetime) -> bool:
    """Is the place open at `now` (any timezone-aware datetime), in Warsaw local time?"""
    hours = parse_opening_hours(opening_hours)
    if hours.get("always"):
        return True
    if hours.get("unknown"):
        return False  # we cannot promise it is open

    local = now.astimezone(TZ)
    t = local.hour * 60 + local.minute
    today = DAYS[local.weekday()]
    yesterday = DAYS[(local.weekday() - 1) % 7]

    if today in hours:
        start, end = (_minutes(x) for x in hours[today])
        if end > start and start <= t < end:
            return True                      # normal day interval
        if end <= start and t >= start:
            return True                      # overnight interval, before midnight
    if yesterday in hours:
        start, end = (_minutes(x) for x in hours[yesterday])
        if end <= start and t < end:
            return True                      # yesterday's overnight interval, after midnight
    return False


def is_24_7(opening_hours: str | dict) -> bool:
    hours = parse_opening_hours(opening_hours)
    if hours.get("always"):
        return True
    return all(hours.get(d) in (["00:00", "24:00"], ["00:00", "00:00"]) for d in DAYS)


def is_night(now: datetime) -> bool:
    h = now.astimezone(TZ).hour
    return h >= NIGHT_START_HOUR or h < NIGHT_END_HOUR


# ---------- search ----------

def route_links(lat: float, lon: float, plat: float, plon: float) -> dict:
    return {
        "osm": f"https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route={lat},{lon};{plat},{plon}",
        "google": f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={plat},{plon}&travelmode=walking",
        "apple": f"https://maps.apple.com/?saddr={lat},{lon}&daddr={plat},{plon}&dirflg=w",
    }


def _result(p: dict, lat: float, lon: float, now: datetime) -> dict:
    """The fields the Urgent card needs for one point."""
    dist = haversine_m(lat, lon, p["lat"], p["lon"])
    return {
        "id": p["id"],
        "name": p["name"],
        "kind": p["kind"],
        "address": p.get("address"),
        "lat": p["lat"],
        "lon": p["lon"],
        "status": p.get("status", "unknown"),
        "minutes_since_confirmed": p.get("minutes_since_confirmed"),
        "distance_m": round(dist),
        "walking_min": round(walking_minutes(dist), 1),
        "entry_fee_pln": p.get("entry_fee_pln"),  # None = fee unknown
        "access": p["access"],
        "open_now": is_open(p["opening_hours"], now),
        "open_24_7": is_24_7(p["opening_hours"]),
        "routes": route_links(lat, lon, p["lat"], p["lon"]),
    }


def find_urgent(points: list[dict], lat: float, lon: float, now: datetime) -> dict:
    """points: point dicts that already have status fields (see status.points_with_status)."""
    night = is_night(now)

    candidates = [
        _result(p, lat, lon, now)
        for p in points
        if p.get("status") in IN_STOCK and p.get("confidence") == "fresh" and p.get("approved", 1)
        and is_open(p["opening_hours"], now)
    ]
    if night:
        # 24/7 places first (False sorts before True), then by walking time.
        candidates.sort(key=lambda c: (not c["open_24_7"], c["walking_min"]))
    else:
        candidates.sort(key=lambda c: c["walking_min"])

    best = candidates[0] if candidates else None
    alternatives = candidates[1:1 + ALTERNATIVES]
    found = best is not None and best["walking_min"] <= MAX_WALK_MIN

    fallback = None
    if not found:
        shops = [_result(p, lat, lon, now) for p in points if p["kind"] in FALLBACK_KINDS]
        shops.sort(key=lambda s: (not s["open_now"], s["walking_min"]))  # open ones first
        fallback = shops[0] if shops else None

    return {
        "found": found,
        "night": night,
        "best": best,               # may be further than 10 min when found is False
        "alternatives": alternatives,
        "fallback": fallback,
        "nearest_min": best["walking_min"] if best else None,
    }


def log_urgent_search(conn: sqlite3.Connection, lat: float, lon: float, result: dict, now: datetime,
                      is_demo: bool = False) -> None:
    """Store one search for the white-spots map. Coordinates are rounded to ~100 m first."""
    conn.execute(
        "INSERT INTO urgent_searches (lat_r, lon_r, found, nearest_min, created_at, is_demo) VALUES (?, ?, ?, ?, ?, ?)",
        (round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS), int(result["found"]),
         result["nearest_min"], to_iso(now), int(is_demo)),
    )
    conn.commit()
