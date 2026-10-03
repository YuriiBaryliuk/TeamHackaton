from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "app": "kropka"}


def test_index_and_static_served():
    assert client.get("/").status_code == 200
    assert client.get("/static/css/styles.css").status_code == 200
