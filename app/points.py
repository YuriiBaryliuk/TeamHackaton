"""Adding a new point from the "Add a point" page.

Rules (simple, explainable):
- only box-hosting kinds can be added (no toilets/pharmacies/shops: those come from data)
- inside one of the supported cities (30 km from its centre); the city is detected
- not within 25 m of an existing point (avoids duplicates and spam)
- at most 3 new points per device per day
- new points are saved with approved = 0: visible on the map with a "waiting for review"
  badge, never recommended by Urgent, until approved with scripts/moderate.py
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta

from app.db import to_iso
from app.cities import CITIES
from app.urgent import haversine_m

ADDABLE_KINDS = ("partner", "pink_box", "school", "university")
DUPLICATE_RADIUS_M = 25
MAX_NEW_POINTS_PER_DAY = 3
USER_ID_START = 2001                 # krk-2001, waw-2001, ... for points added by visitors
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
ALL_DAYS = WEEKDAYS + ["sat", "sun"]


def build_opening_hours(preset: str, open_from: str | None, open_to: str | None) -> dict:
    """'always' -> 24/7; 'daily' / 'weekdays' -> the same hours on those days."""
    if preset == "always":
        return {"always": True}
    if not open_from or not open_to or open_from >= open_to:
        raise ValueError("bad_hours")
    days = ALL_DAYS if preset == "daily" else WEEKDAYS
    return {d: [open_from, open_to] for d in days}


def nearby_point(conn: sqlite3.Connection, lat: float, lon: float) -> str | None:
    """Id of an existing point within DUPLICATE_RADIUS_M, if any."""
    # A cheap box filter in SQL (~0.001 deg is 70-110 m), then the exact distance in Python.
    rows = conn.execute(
        "SELECT id, lat, lon FROM points WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
        (lat - 0.001, lat + 0.001, lon - 0.0015, lon + 0.0015))
    for r in rows:
        if haversine_m(lat, lon, r["lat"], r["lon"]) <= DUPLICATE_RADIUS_M:
            return r["id"]
    return None


def added_today(conn: sqlite3.Connection, device_hash: str, now: datetime) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM points WHERE added_by = ? AND created_at > ?",
        (device_hash, to_iso(now - timedelta(hours=24)))).fetchone()[0]


def next_user_point_id(conn: sqlite3.Connection, prefix: str) -> str:
    pattern = re.compile(rf"{re.escape(prefix)}-(\d+)")
    numbers = [int(m.group(1)) for (pid,) in conn.execute("SELECT id FROM points")
               if (m := pattern.fullmatch(pid)) and int(m.group(1)) >= USER_ID_START]
    return f"{prefix}-{max(numbers, default=USER_ID_START - 1) + 1}"


def insert_point(conn: sqlite3.Connection, data: dict, opening_hours: dict, device_hash: str,
                 now: datetime, city: str) -> str:
    point_id = next_user_point_id(conn, CITIES[city]["prefix"])
    conn.execute(
        """INSERT INTO points (id, name, kind, lat, lon, address, access, entry_fee_pln, opening_hours,
                               wheelchair, has_products, has_qr, city, is_demo, created_at, approved, added_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, 0, ?, 0, ?, 0, ?)""",
        (point_id, data["name"].strip(), data["kind"], round(data["lat"], 6), round(data["lon"], 6),
         (data.get("address") or "").strip() or None, data["access"], json.dumps(opening_hours),
         int(data["wheelchair"]), city, to_iso(now), device_hash))
    conn.commit()
    return point_id
