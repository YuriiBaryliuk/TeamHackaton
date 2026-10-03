from datetime import datetime, timedelta, timezone

from app.status import LOW_AFTER_TAKES, compute_status, points_with_status

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def ev(type_: str, hours_ago: float) -> dict:
    return {"type": type_, "created_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def test_no_events_is_unknown():
    s = compute_status([], NOW)
    assert s["status"] == "unknown"
    assert s["confidence"] == "none"
    assert s["last_confirmed_at"] is None


def test_refilled_is_ok():
    s = compute_status([ev("refilled", 1)], NOW)
    assert s["status"] == "ok"
    assert s["confidence"] == "fresh"
    assert s["minutes_since_confirmed"] == 60


def test_refilled_then_four_takes_still_ok():
    events = [ev("refilled", 5)] + [ev("took", 4 - i * 0.1) for i in range(LOW_AFTER_TAKES - 1)]
    assert compute_status(events, NOW)["status"] == "ok"


def test_refilled_then_five_takes_is_low():
    events = [ev("refilled", 5)] + [ev("took", 4 - i * 0.1) for i in range(5)]
    s = compute_status(events, NOW)
    assert s["status"] == "low"
    assert s["takes_since_refill"] == 5


def test_takes_before_refill_do_not_count():
    events = [ev("took", 10 - i * 0.1) for i in range(8)] + [ev("refilled", 2)]
    s = compute_status(events, NOW)
    assert s["status"] == "ok"
    assert s["takes_since_refill"] == 0


def test_empty_then_took_stays_empty():
    s = compute_status([ev("refilled", 10), ev("empty", 3), ev("took", 1)], NOW)
    assert s["status"] == "empty"
    assert s["confidence"] == "fresh"


def test_refill_after_empty_is_ok_again():
    assert compute_status([ev("empty", 3), ev("refilled", 1)], NOW)["status"] == "ok"


def test_event_order_in_input_does_not_matter():
    s = compute_status([ev("refilled", 1), ev("empty", 3)], NOW)
    assert s["status"] == "ok"


def test_refilled_30h_ago_is_faded():
    s = compute_status([ev("refilled", 30)], NOW)
    assert s["status"] == "ok"
    assert s["confidence"] == "faded"


def test_refilled_80h_ago_is_unknown_and_stale():
    s = compute_status([ev("refilled", 80)], NOW)
    assert s["status"] == "unknown"
    assert s["confidence"] == "stale"


def test_points_with_status_merges_fields():
    points = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
    out = points_with_status(points, {"a": [ev("empty", 1)]}, NOW)
    assert out[0]["status"] == "empty" and out[0]["name"] == "A"
    assert out[1]["status"] == "unknown"
