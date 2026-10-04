from datetime import datetime, timedelta, timezone

from app.stats import (
    compute_stats,
    empty_to_refill_hours,
    grid_cell,
    refill_to_empty_hours,
    white_spots,
)

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def ev(type_, hours):
    return {"type": type_, "created_at": (T0 + timedelta(hours=hours)).isoformat()}


def test_refill_to_empty_cycles():
    events = [ev("refilled", 0), ev("took", 1), ev("empty", 10), ev("refilled", 20), ev("empty", 26)]
    assert refill_to_empty_hours(events) == [10, 6]


def test_top_up_before_empty_measures_from_latest_refill():
    assert refill_to_empty_hours([ev("refilled", 0), ev("refilled", 5), ev("empty", 8)]) == [3]


def test_empty_to_refill_counts_from_first_empty_report():
    events = [ev("empty", 0), ev("empty", 2), ev("refilled", 12), ev("empty", 20), ev("refilled", 23)]
    assert empty_to_refill_hours(events) == [12, 3]


def test_no_cycle_without_both_ends():
    assert refill_to_empty_hours([ev("empty", 1), ev("took", 2)]) == []
    assert empty_to_refill_hours([ev("refilled", 1)]) == []


def test_grid_cell_is_stable_on_boundaries():
    assert grid_cell(50.065, 19.945) == (10013, 3989)
    assert grid_cell(50.0651, 19.9451) == grid_cell(50.0699, 19.9499)


def test_white_spots_count_only_failed_searches():
    searches = ([{"lat_r": 50.068, "lon_r": 19.947, "found": 0}] * 3
                + [{"lat_r": 50.068, "lon_r": 19.947, "found": 1}]
                + [{"lat_r": 50.074, "lon_r": 20.035, "found": 0}])
    points = [{"name": "Station", "lat": 50.0677, "lon": 19.9476}, {"name": "Nowa Huta", "lat": 50.074, "lon": 20.033}]
    spots = white_spots(searches, points)
    assert [(s["count"], s["searches"], s["near"]) for s in spots] == [(3, 4, "Station"), (1, 1, "Nowa Huta")]


def test_landmark_prefers_address_and_skips_unnamed_places():
    searches = [{"lat_r": 52.229, "lon_r": 21.003, "found": 0}]
    points = [{"name": "Toaleta publiczna", "lat": 52.229, "lon": 21.003},
              {"name": "Ziko Apteka", "address": "Aleje Jerozolimskie 54", "lat": 52.2289, "lon": 21.0035},
              {"name": "Dworzec Centralny", "lat": 52.2300, "lon": 21.0100}]
    assert white_spots(searches, points)[0]["near"] == "Aleje Jerozolimskie 54"


def test_cells_where_most_searches_succeed_are_not_white_spots():
    searches = [{"lat_r": 50.061, "lon_r": 19.937, "found": 0}] + [{"lat_r": 50.061, "lon_r": 19.937, "found": 1}] * 4
    assert white_spots(searches, [{"name": "Rynek", "lat": 50.0617, "lon": 19.9373}]) == []


def test_compute_stats_kpis_and_order():
    def point(id_, status="ok", confidence="fresh", has_products=1):
        return {"id": id_, "name": id_, "kind": "partner", "lat": 50, "lon": 20, "status": status,
                "confidence": confidence, "is_demo": 1, "has_products": has_products}
    points = [point("slow"), point("fast"), point("quiet", confidence="faded"), point("toilet", has_products=0)]
    window = {
        "slow": [ev("refilled", 0), ev("took", 1), ev("empty", 30), ev("refilled", 40)],
        "fast": [ev("refilled", 0), ev("took", 1), ev("took", 2), ev("empty", 5), ev("refilled", 9)],
    }
    stats = compute_stats(points, window, [{"lat_r": 50, "lon_r": 20, "found": 0}])
    k = stats["kpis"]
    assert (k["boxes"], k["active_boxes"], k["takes"]) == (3, 2, 3)  # the toilet is not a box
    assert k["fresh_pct"] == 67                                          # 2 of 3 boxes fresh
    assert k["median_empty_to_refill_h"] == 7.0                          # median of 10 h and 4 h
    assert (k["searches"], k["searches_not_found"]) == (1, 1)
    assert [r["id"] for r in stats["boxes"]] == ["fast", "slow", "quiet"]  # fastest-emptying first
    assert stats["boxes"][0]["avg_refill_to_empty_h"] == 5.0
