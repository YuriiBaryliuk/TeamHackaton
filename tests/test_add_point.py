"""Adding a point, moderation, per-point stats. Reuses the API test fixture."""
import pytest

from app import db, points
from app.urgent import find_urgent
from scripts import moderate
from tests.test_api import RYNEK, client, post  # noqa: F401  (client is a pytest fixture)

NEW = {"name": "Kawiarnia na rogu", "kind": "partner", "lat": 50.0645, "lon": 19.9450,
       "access": "ask_staff", "hours": "daily", "open_from": "08:00", "open_to": "20:00"}


def add(client, **changes):
    return client.post("/api/points", json={**NEW, **changes})


def test_add_point_is_pending(client):
    r = add(client)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "krk-2001"
    assert body["point"]["approved"] is False
    assert body["point"]["has_products"] is True
    assert body["point"]["opening_hours"]["sat"] == ["08:00", "20:00"]
    assert add(client, lat=50.0700).json()["id"] == "krk-2002"


def test_point_in_another_city_gets_that_city(client):
    r = add(client, lat=52.2297, lon=21.0122)  # Warsaw
    assert r.status_code == 201
    assert r.json()["id"] == "waw-2001"
    assert client.get("/api/points?city=warszawa").json()["points"][0]["id"] == "waw-2001"
    assert all(p["id"] != "waw-2001" for p in client.get("/api/points?city=krakow").json()["points"])


def test_duplicate_within_25_m_is_rejected(client):
    r = add(client, lat=RYNEK[0] + 0.0001, lon=RYNEK[1])  # ~11 m from the test box
    assert r.status_code == 409
    assert r.json()["detail"] == {"code": "duplicate", "message": "There is already a point here.", "point_id": "box"}


def test_outside_city_and_bad_hours(client):
    assert add(client, lat=51.76, lon=19.46).json()["detail"]["code"] == "outside_city"  # Łódź
    r = add(client, open_from="20:00", open_to="08:00")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "bad_hours"
    assert add(client, kind="city_toilet").status_code == 422   # only box kinds can be added
    assert add(client, open_from="8am").status_code == 422      # HH:MM only


def test_add_limit_per_device(client):
    for i in range(points.MAX_NEW_POINTS_PER_DAY):
        assert add(client, lat=50.050 + i * 0.005).status_code == 201
    r = add(client, lat=50.080)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "add_limit"


def test_pending_point_never_recommended_by_urgent(client):
    pid = add(client, hours="always").json()["id"]
    post(client, pid, type="refilled")
    conn = db.connect()
    from app.main import load_points
    pts = [p for p in load_points(conn, "krakow", db.utc_now()) if p["id"] == pid]
    assert pts[0]["status"] == "ok"
    assert find_urgent(pts, NEW["lat"], NEW["lon"], db.utc_now())["best"] is None
    assert moderate.approve(conn, pid)
    pts = [p for p in load_points(conn, "krakow", db.utc_now()) if p["id"] == pid]
    assert find_urgent(pts, NEW["lat"], NEW["lon"], db.utc_now())["best"]["id"] == pid
    conn.close()


def test_moderation_reject_deletes(client):
    pid = add(client).json()["id"]
    conn = db.connect()
    assert [p["id"] for p in moderate.list_pending(conn)] == [pid]
    assert moderate.reject(conn, pid)
    assert not moderate.reject(conn, "box")  # approved points cannot be rejected this way
    conn.close()
    assert client.get(f"/api/points/{pid}").status_code == 404


def test_point_stats(client):
    post(client, "box", type="refilled")
    post(client, "box", type="took")
    r = client.get("/api/points/box/stats?days=30")
    assert r.status_code == 200
    assert (r.json()["takes"], r.json()["refills"]) == (1, 1)
    assert client.get("/api/points/nope/stats").status_code == 404


@pytest.mark.parametrize("path", ["/add", "/steward", "/partner/box"])
def test_new_pages(client, path):
    assert client.get(path).status_code == 200


def test_partner_page_unknown_point(client):
    assert client.get("/partner/nope").status_code == 404
