"""Pilot operations: deletion drill, readiness check, Render URL defaults, the self-generated badge signing key."""

from app.db import SessionLocal


def test_deletion_drill_leaves_no_trace(client, capsys):
    from app import manage

    assert manage.deletion_drill() == 0
    out = capsys.readouterr().out
    assert "[PASS] no trace left" in out and "[FAIL]" not in out


def test_pilot_check_reports_what_is_missing(client, capsys):
    from app import manage

    assert manage.pilot_check() == 1                       # the test server is not a production deployment
    out = capsys.readouterr().out
    assert "[FAIL] ENV is development" in out and "demo accounts" in out and "NOT READY" in out


def test_render_url_becomes_app_url(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://cometiq-pilot.onrender.com")
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    s = get_settings.__wrapped__()
    assert s.APP_URL == "https://cometiq-pilot.onrender.com" and s.CORS_ORIGINS == s.APP_URL
    monkeypatch.setenv("APP_URL", "https://cometiq.utdallas.edu")           # a custom domain wins
    assert get_settings.__wrapped__().APP_URL == "https://cometiq.utdallas.edu"


def test_production_generates_and_keeps_one_signing_key(client, monkeypatch):
    from app.config import get_settings
    from app.integrations import openbadges as ob
    from app.models import AppSecret

    s = get_settings()
    monkeypatch.setattr(s, "ENV", "production")
    monkeypatch.setattr(s, "SECRETS_KEY", "a-production-secrets-key-that-is-long-enough")
    monkeypatch.setattr(s, "OB_SIGNING_KEY", "")
    monkeypatch.setattr(s, "OB_SIGNING_KEY_FILE", "")
    ob.signing_key.cache_clear()
    try:
        kid = ob.public_jwk()["kid"]
        with SessionLocal() as db:
            row = db.get(AppSecret, "ob_signing_key")
            assert row and "PRIVATE KEY" not in row.value                    # stored encrypted
        ob.signing_key.cache_clear()
        assert ob.public_jwk()["kid"] == kid                                  # same key after a restart
        assert ob.status()["source"] == "generated, stored encrypted in the database"
        monkeypatch.setattr(s, "SECRETS_KEY", "a-different-secrets-key-that-is-long-enough")
        ob.signing_key.cache_clear()
        try:
            ob.signing_key()
            raise AssertionError("expected Unavailable")
        except ob.Unavailable as e:
            assert "SECRETS_KEY changed" in str(e)
    finally:
        ob.signing_key.cache_clear()
        with SessionLocal() as db:
            db.query(AppSecret).delete()
            db.commit()
