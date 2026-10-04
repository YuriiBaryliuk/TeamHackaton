"""Aggregations for the city dashboard. Anonymous by design: we only count events
per box and Urgent searches per ~500 m grid cell. No person can be followed.

compute_stats() is pure (no database), load_stats() reads the database and calls it.
"""
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from app.db import fetch_events_by_point, fetch_points, to_iso
from app.status import parse_ts, points_with_status
from app.urgent import CITY_CENTRES, LOG_RADIUS_M, haversine_m

GRID_DEG = 0.005          # white-spot grid cell, about 550 m x 360 m in Kraków
TOP_WHITE_SPOTS = 30
WHITE_SPOT_MIN_SHARE = 0.5   # a cell is a white spot if at least half of its searches found nothing


# ---------- cycles of one box ----------

def refill_to_empty_hours(events: list[dict]) -> list[float]:
    """Hours from a refill to the next "empty" report (how fast a box runs out).
    If a box is topped up again before it runs out, we measure from the latest refill."""
    out, last_refill = [], None
    for e in events:
        t = parse_ts(e["created_at"])
        if e["type"] == "refilled":
            last_refill = t
        elif e["type"] == "empty" and last_refill is not None:
            out.append((t - last_refill).total_seconds() / 3600)
            last_refill = None
    return out


def empty_to_refill_hours(events: list[dict]) -> list[float]:
    """Hours from the first "empty" report to the next refill (how long people wait)."""
    out, first_empty = [], None
    for e in events:
        t = parse_ts(e["created_at"])
        if e["type"] == "empty" and first_empty is None:
            first_empty = t
        elif e["type"] == "refilled" and first_empty is not None:
            out.append((t - first_empty).total_seconds() / 3600)
            first_empty = None
    return out


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


# ---------- white spots ----------

def grid_cell(lat: float, lon: float) -> tuple[int, int]:
    # round() first so 50.065 / 0.005 does not become 10012.9999 because of floats
    return math.floor(round(lat / GRID_DEG, 6)), math.floor(round(lon / GRID_DEG, 6))


def white_spots(searches: list[dict], points: list[dict]) -> list[dict]:
    """Group searches that found nothing nearby into grid cells, biggest first.
    Only cells where most searches failed count: a busy area where 1 in 10 searches
    fails is served fine, a place where people usually find nothing is a white spot."""
    failed = Counter(grid_cell(s["lat_r"], s["lon_r"]) for s in searches if not s["found"])
    total = Counter(grid_cell(s["lat_r"], s["lon_r"]) for s in searches)
    cells = [(cell, n) for cell, n in failed.most_common() if n / total[cell] >= WHITE_SPOT_MIN_SHARE]
    spots = []
    for (i, j), count in cells[:TOP_WHITE_SPOTS]:
        lat, lon = (i + 0.5) * GRID_DEG, (j + 0.5) * GRID_DEG
        near = min(points, key=lambda p: haversine_m(lat, lon, p["lat"], p["lon"]), default=None)
        spots.append({
            "lat": round(lat, 5), "lon": round(lon, 5), "count": count, "searches": total[(i, j)],
            "near": near["name"] if near else None,  # a landmark so people know where it is
        })
    return spots


# ---------- everything ----------

def box_activity(events: list[dict]) -> dict:
    """Counts and average cycle times for one box (events of the period, oldest first)."""
    kinds = Counter(e["type"] for e in events)
    runs_out = refill_to_empty_hours(events)
    return {
        "takes": kinds["took"], "empties": kinds["empty"], "refills": kinds["refilled"],
        "cycles": len(runs_out),
        "avg_refill_to_empty_h": _avg(runs_out),
        "avg_empty_to_refill_h": _avg(empty_to_refill_hours(events)),
    }


def compute_stats(points: list[dict], window_events: dict[str, list[dict]], searches: list[dict]) -> dict:
    """points: with current status. window_events: events in the period, per point, oldest first."""
    boxes = [p for p in points if p["has_products"]]
    rows, all_waits = [], []
    for p in boxes:
        ev = window_events.get(p["id"], [])
        all_waits += empty_to_refill_hours(ev)
        rows.append({
            "id": p["id"], "name": p["name"], "kind": p["kind"], "lat": p["lat"], "lon": p["lon"],
            "status": p["status"], "confidence": p["confidence"], "is_demo": bool(p["is_demo"]),
            **box_activity(ev),
        })
    # Fastest-emptying first; boxes that never ran out go last.
    rows.sort(key=lambda r: (r["avg_refill_to_empty_h"] is None, r["avg_refill_to_empty_h"] or 0, -r["takes"]))

    not_found = sum(1 for s in searches if not s["found"])
    kpis = {
        "boxes": len(boxes),
        "active_boxes": sum(1 for r in rows if r["takes"] + r["empties"] + r["refills"] > 0),
        "fresh_pct": round(100 * sum(1 for p in boxes if p["confidence"] == "fresh") / len(boxes)) if boxes else 0,
        "takes": sum(r["takes"] for r in rows),
        "median_empty_to_refill_h": round(median(all_waits), 1) if all_waits else None,
        "searches": len(searches),
        "searches_not_found": not_found,
    }
    return {"kpis": kpis, "white_spots": white_spots(searches, points), "boxes": rows}


def load_point_stats(conn: sqlite3.Connection, point_id: str, days: int) -> dict:
    """Activity of one point in the last `days` days (for the partner page)."""
    since = to_iso(datetime.now(timezone.utc) - timedelta(days=days))
    events = [dict(r) for r in conn.execute(
        "SELECT type, created_at FROM events WHERE point_id = ? AND created_at >= ? ORDER BY created_at",
        (point_id, since))]
    return {"id": point_id, "days": days, **box_activity(events)}


def load_stats(conn: sqlite3.Connection, city: str, days: int, now: datetime) -> dict:
    since = to_iso(now - timedelta(days=days))
    points = points_with_status(fetch_points(conn, city), fetch_events_by_point(conn, city), now)

    window_events: dict[str, list[dict]] = defaultdict(list)
    rows = conn.execute(
        """SELECT e.point_id, e.type, e.created_at, e.is_demo FROM events e
           JOIN points p ON p.id = e.point_id
           WHERE p.city = ? AND e.created_at >= ? ORDER BY e.created_at""", (city, since))
    demo_events = False
    for r in rows:
        window_events[r["point_id"]].append(dict(r))
        demo_events = demo_events or bool(r["is_demo"])

    # urgent_searches has no city column: keep the ones within the city radius.
    centre = CITY_CENTRES.get(city)
    searches = [
        dict(r) for r in conn.execute(
            "SELECT lat_r, lon_r, found, is_demo FROM urgent_searches WHERE created_at >= ?", (since,))
        if centre and haversine_m(r["lat_r"], r["lon_r"], *centre) <= LOG_RADIUS_M
    ]

    stats = compute_stats(points, window_events, searches)
    stats.update(
        city=city, days=days, generated_at=to_iso(now),
        has_demo_data=demo_events or any(p["is_demo"] for p in points) or any(s["is_demo"] for s in searches),
    )
    return stats
