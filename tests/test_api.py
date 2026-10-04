"""API tests against a fresh temporary database."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import abuse, db
from app.main import app

RYNEK = (50.0617, 19.9373)
ALWAYS = json.dumps({"always": True})


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    conn = db.connect()
    db.init_db(conn)
    now = db.to_iso(db.utc_now())
    conn.executemany(
        """INSERT INTO points (id, name, kind, lat, lon, address, access, opening_hours, has_products, created_at)
           VALUES (?, ?, ?, ?, ?, '', 'open', ?, ?, ?)""",
        [
            ("box", "Box at Rynek", "partner", RYNEK[0], RYNEK[1], ALWAYS, 1, now),
            ("box2", "Second box", "partner", RYNEK[0] + 0.003, RYNEK[1], ALWAYS, 1, now),
            ("pharm", "Pharmacy", "pharmacy", 50.0717, 20.0373, ALWAYS, 0, now),
        ],
    )
    conn.commit()
    conn.close()
    with TestClient(app) as c:  # runs the startup code too
        yield c


def post(client, point_id, **body):
    return client.post(f"/api/points/{point_id}/events", json=body)


def test_get_point(client):
    r = client.get("/api/points/box")
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
    assert r.json()["open_now"] is True


def test_unknown_point_is_404(client):
    assert client.get("/api/points/nope").status_code == 404
    assert post(client, "nope", type="took").status_code == 404
    assert client.get("/p/nope").status_code == 404


def test_point_page_served(client):
    r = client.get("/p/box")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_event_changes_status_and_sets_cookie(client):
    r = post(client, "box", type="refilled")
    assert r.status_code == 200
    assert r.json()["point"]["status"] == "ok"
    assert r.json()["point"]["confidence"] == "fresh"
    assert abuse.DEVICE_COOKIE in r.cookies

    r = post(client, "box", type="empty")
    assert r.json()["point"]["status"] == "empty"


def test_took_is_refused_on_an_empty_box(client):
    post(client, "box", type="refilled")
    post(client, "box", type="empty")
    r = post(client, "box", type="took")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "box_empty"
    client.cookies.clear()                                           # another person (no rate limit clash)
    assert post(client, "box", type="refilled").status_code == 200   # refill is still possible
    assert post(client, "box", type="took").status_code == 200       # and then taking again


def test_same_event_twice_is_rate_limited(client):
    assert post(client, "box", type="took").status_code == 200
    r = post(client, "box", type="took")
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_soon"
    assert int(r.headers["Retry-After"]) > 500
    # Other types and other points are still fine.
    assert post(client, "box", type="empty").status_code == 200
    assert post(client, "box2", type="took").status_code == 200


def test_new_browser_is_not_blocked_by_another(client):
    assert post(client, "box", type="took").status_code == 200
    client.cookies.clear()
    assert post(client, "box", type="took").status_code == 200


def test_daily_limit(client):
    device_id = str(uuid.uuid4())
    client.cookies.set(abuse.DEVICE_COOKIE, device_id)
    conn = db.connect()
    for _ in range(abuse.DAILY_LIMIT):
        db.insert_event(conn, "box2", "took", "qr", abuse.hash_device(device_id), db.utc_now())
    conn.close()
    r = post(client, "box", type="refilled")
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "daily_limit"


def test_geo_source_needs_location_near_the_point(client):
    assert post(client, "box", type="took", source="geo").status_code == 400
    far = post(client, "box", type="took", source="geo", lat=RYNEK[0] + 0.01, lon=RYNEK[1])  # ~1.1 km
    assert far.status_code == 403 and far.json()["detail"]["code"] == "too_far"
    near = post(client, "box", type="took", source="geo", lat=RYNEK[0] + 0.0005, lon=RYNEK[1])  # ~55 m
    assert near.status_code == 200


def test_invalid_event_type_is_422(client):
    assert post(client, "box", type="stolen").status_code == 422


def test_urgent_finds_fresh_point(client):
    post(client, "box", type="refilled")
    r = client.post("/api/urgent", json={"lat": RYNEK[0] + 0.001, "lon": RYNEK[1]})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True and body["best"]["id"] == "box"


def test_urgent_far_away_gives_fallback_and_is_logged(client):
    post(client, "box", type="refilled")
    r = client.post("/api/urgent", json={"lat": 50.0717, "lon": 20.0373})  # Nowa Huta
    body = r.json()
    assert body["found"] is False
    assert body["fallback"]["id"] == "pharm"
    conn = db.connect()
    row = conn.execute("SELECT lat_r, lon_r, found FROM urgent_searches").fetchone()
    conn.close()
    assert tuple(row) == (50.072, 20.037, 0)


def test_urgent_outside_city_is_not_logged(client):
    r = client.post("/api/urgent", json={"lat": 51.76, "lon": 19.46})  # Łódź: no supported city
    assert r.json()["city"] == "krakow"
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM urgent_searches").fetchone()[0] == 0
    conn.close()


def test_cities_endpoint(client):
    ids = [c["id"] for c in client.get("/api/cities").json()]
    assert ids == ["krakow", "warszawa", "wroclaw", "gdansk"]


def test_unknown_city_is_404(client):
    assert client.get("/api/points?city=atlantis").json()["detail"]["code"] == "city_not_found"
    assert client.get("/api/city/stats?city=atlantis").status_code == 404


def test_urgent_detects_city_from_location(client):
    conn = db.connect()
    conn.execute("""INSERT INTO points (id, name, kind, lat, lon, access, opening_hours, has_products, city, created_at)
                    VALUES ('waw-box', 'Warsaw box', 'partner', 52.2300, 21.0100, 'open', ?, 1, 'warszawa', ?)""",
                 (ALWAYS, db.to_iso(db.utc_now())))
    conn.commit()
    conn.close()
    post(client, "waw-box", type="refilled")
    # The map may show Kraków (default city param), but the person is in Warsaw.
    r = client.post("/api/urgent", json={"lat": 52.2310, "lon": 21.0110}).json()
    assert r["city"] == "warszawa"
    assert r["found"] is True and r["best"]["id"] == "waw-box"


def test_city_stats(client):
    post(client, "box", type="refilled")
    post(client, "box", type="took")
    client.post("/api/urgent", json={"lat": 50.0717, "lon": 20.0373})  # nothing nearby -> white spot
    r = client.get("/api/city/stats?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["kpis"]["takes"] == 1
    assert body["kpis"]["boxes"] == 2
    assert body["white_spots"][0]["count"] == 1
    assert body["has_demo_data"] is False
    assert client.get("/api/city/stats?days=0").status_code == 422


def test_city_stats_csv(client):
    post(client, "box", type="took")
    r = client.get("/api/city/stats.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("id,name,kind,status,takes")
    assert len(lines) == 3  # header + 2 boxes


def test_parallel_requests_do_not_crash(client):
    """Regression: the DB connection is opened in one worker thread and may be used in another."""
    from concurrent.futures import ThreadPoolExecutor
    paths = ["/api/points/box", "/api/points/box/stats", "/api/points", "/api/points/box2"] * 10
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda p: client.get(p).status_code, paths))
    assert codes == [200] * len(paths)


def test_docs_and_openapi(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/points", "/api/points/{point_id}", "/api/points/{point_id}/events", "/api/urgent"} <= set(paths)
