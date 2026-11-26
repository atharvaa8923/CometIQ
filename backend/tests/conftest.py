import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""  # always test the deterministic built-in engine
os.environ["JOB_SYNC_ENABLED"] = "false"
os.environ["TASKS_INLINE"] = "true"
os.environ["RETENTION_ENABLED"] = "false"  # background tasks run synchronously in tests
os.environ.setdefault("RATE_LIMIT_MULTIPLIER", "50")  # tests call endpoints far faster than people do; one test checks the real limits
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256!!"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PW = "CometIQ2026!"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    out = {}
    for role in ("admin", "faculty", "student", "employer", "advisor"):
        r = client.post("/api/auth/login", json={"email": f"{role}@cometiq.app", "password": PW})
        assert r.status_code == 200, r.text
        out[role] = {"Authorization": f"Bearer {r.json()['token']}"}
    return out
