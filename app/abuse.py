"""Simple, explainable anti-abuse rules (spec section 5.3).

- Each browser gets a random id in the cookie `kropka_did`. We never store the
  id itself, only SHA-256(server salt + id). It is not personal data and is used
  only for rate limiting.
- One event of the same type per point per device per 10 minutes.
- At most 30 events per device per 24 hours.
- Events with source 'geo' must come from within 150 m of the point. The
  coordinates are checked and then thrown away, never stored.

Known limit: clearing cookies gives a new id. Good enough for a hackathon MVP.
"""
import hashlib
import math
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

from app.db import to_iso
from app.status import parse_ts
from app.urgent import haversine_m

DEVICE_COOKIE = "kropka_did"
COOKIE_MAX_AGE_S = 365 * 24 * 3600
SAME_EVENT_WINDOW = timedelta(minutes=10)
DAILY_WINDOW = timedelta(hours=24)
DAILY_LIMIT = 30
GEO_MAX_DISTANCE_M = 150

DEVICE_SALT = os.environ.get("DEVICE_SALT", "dev-only-salt-set-DEVICE_SALT-in-production")


def new_device_id() -> str:
    return str(uuid.uuid4())


def is_valid_device_id(value: str | None) -> bool:
    try:
        uuid.UUID(value or "")
        return True
    except ValueError:
        return False


def hash_device(device_id: str, salt: str = DEVICE_SALT) -> str:
    return hashlib.sha256(f"{salt}:{device_id}".encode()).hexdigest()


def check_rate_limit(conn: sqlite3.Connection, device_hash: str, point_id: str, type_: str,
                     now: datetime) -> dict | None:
    """None if the event is allowed, otherwise an error dict {code, message, retry_after_s}."""
    last_same = conn.execute(
        """SELECT MAX(created_at) FROM events
           WHERE device_hash = ? AND point_id = ? AND type = ? AND created_at > ?""",
        (device_hash, point_id, type_, to_iso(now - SAME_EVENT_WINDOW)),
    ).fetchone()[0]
    if last_same:
        wait = SAME_EVENT_WINDOW - (now - parse_ts(last_same))
        return {
            "code": "too_soon",
            "message": "Thanks, we already have your mark for this box. You can mark it again in a few minutes.",
            "retry_after_s": max(1, math.ceil(wait.total_seconds())),
        }

    first_today, count_today = conn.execute(
        "SELECT MIN(created_at), COUNT(*) FROM events WHERE device_hash = ? AND created_at > ?",
        (device_hash, to_iso(now - DAILY_WINDOW)),
    ).fetchone()
    if count_today >= DAILY_LIMIT:
        wait = DAILY_WINDOW - (now - parse_ts(first_today))
        return {
            "code": "daily_limit",
            "message": "Thank you for helping so much today! The daily limit of marks is reached, see you tomorrow.",
            "retry_after_s": max(1, math.ceil(wait.total_seconds())),
        }
    return None


def check_geo(point: dict, lat: float | None, lon: float | None) -> dict | None:
    """For source='geo': None if the user is within 150 m of the point, otherwise an error dict."""
    if lat is None or lon is None:
        return {"code": "location_required", "message": "This kind of mark needs your location."}
    if haversine_m(lat, lon, point["lat"], point["lon"]) > GEO_MAX_DISTANCE_M:
        return {"code": "too_far", "message": "It looks like you are not next to this box. Scan its QR code instead."}
    return None
