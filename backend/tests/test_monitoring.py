"""Health/readiness, request IDs, error handling and Sentry scrubbing."""
from fastapi.testclient import TestClient

from app.main import app
from app.monitoring import _scrub
from app.services import gap as gapsvc


def test_health_ready_and_request_id(client):
    r = client.get("/api/health/ready")
    assert r.status_code == 200 and r.json()["database"] == "ok" and "tasks" in r.json()
    assert r.headers["X-Request-ID"]
    assert client.get("/api/health", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"


def test_unhandled_error_returns_reference(tokens, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("database exploded with secret details")

    monkeypatch.setattr(gapsvc, "market_demand", boom)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/gap/market", headers=tokens["faculty"])
    assert r.status_code == 500
    body = r.json()
    assert "secret" not in body["detail"] and body["request_id"] == r.headers["X-Request-ID"]


def test_client_error_endpoint_rate_limited(client):
    for _ in range(12):
        assert client.post("/api/client-errors", content=b'{"message":"x"}').status_code == 204


def test_sentry_scrubs_personal_data():
    ev = {"request": {"data": {"password": "p"}, "cookies": {"s": "1"}, "headers": {"Authorization": "Bearer t", "Accept": "x"}},
          "user": {"email": "a@b.c"}}
    out = _scrub(ev, None)
    assert "data" not in out["request"] and "cookies" not in out["request"] and "user" not in out
    assert out["request"]["headers"]["Authorization"] == "[removed]" and out["request"]["headers"]["Accept"] == "x"
