"""Status and freshness of a point. Pure functions: no database, no clock.

The caller passes the events and "now", which makes everything easy to test.

Status is decided by the latest 'refilled' or 'empty' event:
    refilled -> ok, empty -> empty, neither -> unknown
'took' events after a refill count down the stock: 5 or more -> low.
A 'took' after 'empty' does not make it ok again (only a refill does);
it is just a demand signal.

Freshness ("honest map") depends on the newest event of any type:
    < 24 h        -> fresh
    24 h to 72 h  -> faded (shown pale)
    > 72 h        -> stale, and status is shown as unknown
A point without any events is unknown. For a point with has_products = 0
this means "hygiene products not confirmed here".
"""
from datetime import datetime, timezone

LOW_AFTER_TAKES = 5   # this many 'took' after a refill -> status 'low'
FRESH_HOURS = 24      # younger than this -> fresh
STALE_HOURS = 72      # older than this -> unknown / stale

STATE_EVENTS = ("refilled", "empty")


def parse_ts(value: str | datetime) -> datetime:
    """ISO string or datetime -> timezone-aware UTC datetime."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # we only ever store UTC
    return dt.astimezone(timezone.utc)


def compute_status(events: list[dict], now: datetime) -> dict:
    """events: dicts with 'type' and 'created_at'. Returns the status of one point.

    confidence is one of: 'fresh', 'faded', 'stale', 'none' (no events at all).
    """
    if not events:
        return {
            "status": "unknown",
            "confidence": "none",
            "last_confirmed_at": None,
            "minutes_since_confirmed": None,
            "takes_since_refill": 0,
        }

    events = sorted(events, key=lambda e: parse_ts(e["created_at"]))

    # Index of the latest refilled/empty event, if any.
    last_state = None
    for i, e in enumerate(events):
        if e["type"] in STATE_EVENTS:
            last_state = i

    if last_state is None:
        status = "unknown"
        later = events
    else:
        status = "ok" if events[last_state]["type"] == "refilled" else "empty"
        later = events[last_state + 1:]

    takes = sum(1 for e in later if e["type"] == "took")
    if status == "ok" and takes >= LOW_AFTER_TAKES:
        status = "low"

    last_confirmed = parse_ts(events[-1]["created_at"])
    age_hours = max(0.0, (now - last_confirmed).total_seconds() / 3600)

    if age_hours < FRESH_HOURS:
        confidence = "fresh"
    elif age_hours <= STALE_HOURS:
        confidence = "faded"
    else:
        confidence = "stale"
        status = "unknown"  # too old to trust: be honest and show unknown

    return {
        "status": status,
        "confidence": confidence,
        "last_confirmed_at": last_confirmed.isoformat(timespec="seconds"),
        "minutes_since_confirmed": int(age_hours * 60),
        "takes_since_refill": takes,
    }


def points_with_status(points: list[dict], events_by_point: dict[str, list[dict]], now: datetime) -> list[dict]:
    """Attach the computed status fields to every point dict."""
    return [{**p, **compute_status(events_by_point.get(p["id"], []), now)} for p in points]
