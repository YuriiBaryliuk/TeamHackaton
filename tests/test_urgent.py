from datetime import datetime, timezone

import pytest

from app.db import connect, init_db
from app.urgent import (
    find_urgent,
    haversine_m,
    is_24_7,
    is_night,
    is_open,
    log_urgent_search,
    walking_minutes,
)

# October 2026: Warsaw is UTC+2 (summer time until 25 Oct).
MON_NOON = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)   # Monday 12:00 Warsaw
RYNEK = (50.0617, 19.9373)                                      # Kraków Main Square

WEEKDAYS_9_17 = {d: ["09:00", "17:00"] for d in ["mon", "tue", "wed", "thu", "fri"]}
ALWAYS = {"always": True}


# ---------- geometry ----------

def test_haversine_zero():
    assert haversine_m(*RYNEK, *RYNEK) == 0


def test_haversine_one_degree_latitude():
    assert haversine_m(50, 20, 51, 20) == pytest.approx(111_195, abs=50)


def test_haversine_krakow_warsaw():
    # Kraków Main Square to the Palace of Culture in Warsaw: about 252 km.
    assert 248_000 < haversine_m(*RYNEK, 52.2318, 21.0060) < 256_000


def test_walking_minutes():
    assert walking_minutes(800) == pytest.approx(13.0)  # 800 * 1.3 / 80


# ---------- opening hours ----------

def test_always_open():
    assert is_open(ALWAYS, MON_NOON)
    assert is_open('{"always": true}', MON_NOON)  # JSON text works too


def test_open_during_hours_in_warsaw_time():
    # 07:30 UTC is 09:30 in Warsaw: open. Naive UTC would wrongly say closed.
    assert is_open(WEEKDAYS_9_17, datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc))
    # 15:30 UTC is 17:30 in Warsaw: closed.
    assert not is_open(WEEKDAYS_9_17, datetime(2026, 10, 5, 15, 30, tzinfo=timezone.utc))


def test_closing_time_is_exclusive():
    assert not is_open(WEEKDAYS_9_17, datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc))  # 17:00 local


def test_closed_day():
    sunday_noon = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc)
    assert not is_open(WEEKDAYS_9_17, sunday_noon)


def test_overnight_hours():
    club = {"sat": ["18:00", "02:00"]}
    assert is_open(club, datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc))      # Sat 19:00
    assert is_open(club, datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc))      # Sun 01:00
    assert not is_open(club, datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc))   # Sun 03:00
    assert not is_open(club, datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc))  # Sun 19:00


def test_closing_at_midnight_written_as_24():
    late = {"mon": ["10:00", "24:00"]}
    assert is_open(late, datetime(2026, 10, 5, 21, 30, tzinfo=timezone.utc))     # Mon 23:30


def test_is_24_7():
    assert is_24_7(ALWAYS)
    assert is_24_7({d: ["00:00", "24:00"] for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})
    assert not is_24_7(WEEKDAYS_9_17)


def test_is_night():
    assert is_night(datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc))      # 23:00 local
    assert is_night(datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc))       # 05:00 local
    assert not is_night(MON_NOON)


# ---------- search ----------

def point(id_, lat, lon, status="ok", confidence="fresh", kind="partner", hours=ALWAYS):
    return {
        "id": id_, "name": id_, "kind": kind, "lat": lat, "lon": lon, "address": None,
        "access": "open", "entry_fee_pln": 0, "opening_hours": hours,
        "status": status, "confidence": confidence, "minutes_since_confirmed": 15,
    }


def test_nearest_in_stock_point_wins():
    points = [
        point("far", RYNEK[0] + 0.006, RYNEK[1]),     # ~670 m
        point("near", RYNEK[0] + 0.003, RYNEK[1]),    # ~330 m
        point("low", RYNEK[0] + 0.004, RYNEK[1], status="low"),
    ]
    r = find_urgent(points, *RYNEK, MON_NOON)
    assert r["found"] is True
    assert r["best"]["id"] == "near"
    assert [a["id"] for a in r["alternatives"]] == ["low", "far"]
    assert r["fallback"] is None
    assert "fossgis_osrm_foot" in r["best"]["routes"]["osm"]


def test_empty_faded_and_closed_points_are_skipped():
    points = [
        point("empty", RYNEK[0] + 0.001, RYNEK[1], status="empty"),
        point("faded", RYNEK[0] + 0.001, RYNEK[1], confidence="faded"),
        point("closed", RYNEK[0] + 0.001, RYNEK[1], hours={"sun": ["10:00", "12:00"]}),
        point("ok", RYNEK[0] + 0.005, RYNEK[1]),
    ]
    r = find_urgent(points, *RYNEK, MON_NOON)
    assert r["best"]["id"] == "ok"
    assert r["alternatives"] == []


def test_nothing_within_10_min_returns_fallback():
    nowa_huta = (50.0717, 20.0373)  # ~7 km from the Main Square
    points = [
        point("rynek-box", *RYNEK),
        point("closed-shop", nowa_huta[0] + 0.001, nowa_huta[1], kind="shop", status="unknown",
              hours={"sun": ["10:00", "12:00"]}),
        point("pharmacy", nowa_huta[0] + 0.003, nowa_huta[1], kind="pharmacy", status="unknown"),
    ]
    r = find_urgent(points, *nowa_huta, MON_NOON)
    assert r["found"] is False
    assert r["best"]["id"] == "rynek-box"          # still shown, but it is a long walk
    assert r["nearest_min"] > 10
    assert r["fallback"]["id"] == "pharmacy"       # open one beats the nearer closed one
    assert r["fallback"]["open_now"] is True


def test_no_candidates_at_all_still_gives_fallback():
    points = [point("pharmacy", RYNEK[0] + 0.002, RYNEK[1], kind="pharmacy", status="unknown")]
    r = find_urgent(points, *RYNEK, MON_NOON)
    assert r["found"] is False
    assert r["best"] is None
    assert r["nearest_min"] is None
    assert r["fallback"]["id"] == "pharmacy"


def test_night_prefers_24_7_places():
    mon_23h = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
    points = [
        point("bar", RYNEK[0] + 0.001, RYNEK[1], hours={"mon": ["10:00", "24:00"]}),
        point("station", RYNEK[0] + 0.006, RYNEK[1], hours=ALWAYS),
    ]
    r = find_urgent(points, *RYNEK, mon_23h)
    assert r["night"] is True
    assert r["best"]["id"] == "station"
    # In the daytime the nearer one wins.
    assert find_urgent(points, *RYNEK, MON_NOON)["best"]["id"] == "bar"


def test_log_rounds_coordinates():
    conn = connect(":memory:")
    init_db(conn)
    log_urgent_search(conn, 50.061749, 19.937321, {"found": False, "nearest_min": 12.3}, MON_NOON)
    row = conn.execute("SELECT * FROM urgent_searches").fetchone()
    assert (row["lat_r"], row["lon_r"]) == (50.062, 19.937)
    assert row["found"] == 0
    assert row["nearest_min"] == 12.3
