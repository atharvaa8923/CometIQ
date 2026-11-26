"""CometIQ inside Canvas: LTI 1.3 launch against a fake Canvas platform that signs real launch tokens."""
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app import integrations
from app.config import get_settings
from test_institution import FakeBadgr, FakeCanvas, FakeIdP, _connect_canvas

C = "https://purl.imsglobal.org/spec/lti/claim/"
ISS, CLIENT = "https://canvas.instructure.com", "10000000000042"
INSTRUCTOR = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
LEARNER = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"


class FakePlatform:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def __call__(self, req):
        if req.url.path == "/api/lti/security/jwks":
            return httpx.Response(200, json={"keys": [{**json.loads(RSAAlgorithm.to_jwk(self.key.public_key())), "kid": "canvas-1"}]})
        return httpx.Response(404)

    def token(self, nonce, **over):
        now = int(time.time())
        claims = {"iss": ISS, "aud": CLIENT, "sub": "canvas-user-1", "iat": now, "exp": now + 300, "nonce": nonce,
                  "email": "prof.lti@utdallas.edu", "name": "Prof LTI", C + "version": "1.3.0",
                  C + "message_type": "LtiResourceLinkRequest", C + "deployment_id": "1:abc", C + "roles": [INSTRUCTOR],
                  C + "context": {"id": "ctx1", "label": "BUAN 6320", "title": "Database Foundations"},
                  C + "custom": {"canvas_course_id": "101", "canvas_user_id": "42"}}
        claims |= over
        key = over.pop("_key", None) if "_key" in over else None
        claims.pop("_key", None)
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": "canvas-1"})


@pytest.fixture
def platform(monkeypatch):
    from app.integrations import lti, sso

    p, canvas = FakePlatform(), FakeCanvas()
    hosts = {"sso.canvas.test": p, "canvas.test": canvas, "idp.test": FakeIdP(), "badgr.test": FakeBadgr()}
    monkeypatch.setattr(integrations, "_transport", httpx.MockTransport(lambda req: hosts[req.url.host](req)))
    s = get_settings()
    for k, v in {"LTI_ENABLED": True, "LTI_CLIENT_ID": CLIENT, "LTI_ISSUER": ISS, "LTI_AUTH_URL": "https://sso.canvas.test/api/lti/authorize_redirect",
                 "LTI_JWKS_URL": "https://sso.canvas.test/api/lti/security/jwks", "LTI_DEPLOYMENT_IDS": "",
                 "CANVAS_BASE_URL": "https://canvas.test", "CANVAS_CLIENT_ID": "1", "CANVAS_CLIENT_SECRET": "x"}.items():
        monkeypatch.setattr(s, k, v)
    lti._jwks.clear()
    sso._jwks.clear()
    yield p
    lti._jwks.clear()


def start(client) -> dict:
    r = client.post("/api/lti/login", data={"iss": ISS, "login_hint": "hint-1", "target_link_uri": "http://localhost:8000/api/lti/launch",
                                            "client_id": CLIENT, "lti_message_hint": "msg-1"}, follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(loc.query).items()}
    assert loc.netloc == "sso.canvas.test" and q["response_mode"] == "form_post" and q["prompt"] == "none" and q["scope"] == "openid"
    assert q["login_hint"] == "hint-1" and q["lti_message_hint"] == "msg-1" and q["redirect_uri"].endswith("/api/lti/launch")
    return q


def launch(client, platform, **over):
    q = start(client)
    tok = platform.token(over.pop("nonce", q["nonce"]), **over)
    return client.post("/api/lti/launch", data={"id_token": tok, "state": q["state"]}, follow_redirects=False), tok, q


def session(r) -> dict:
    loc = urlparse(r.headers["location"])
    assert r.status_code == 303 and loc.path == "/sso/complete", r.text
    frag = {k: v[0] for k, v in parse_qs(loc.fragment).items()}
    return {"h": {"Authorization": f"Bearer {frag['token']}"}, "next": frag["next"]}


def test_tool_config_for_canvas(client):
    cfg = client.get("/api/lti/config.json").json()
    assert cfg["oidc_initiation_url"].endswith("/api/lti/login") and cfg["target_link_uri"].endswith("/api/lti/launch")
    place = cfg["extensions"][0]["settings"]["placements"][0]
    assert place["placement"] == "course_navigation" and cfg["custom_fields"]["canvas_course_id"] == "$Canvas.course.id"
    assert cfg["extensions"][0]["privacy_level"] == "public" and cfg["public_jwk_url"].endswith("/api/public/ob/jwks.json")


def test_launch_signs_in_instructor_and_student_and_shows_the_course(client, tokens, platform):
    fac = tokens["faculty"]
    _connect_canvas(client, fac)                                   # a faculty member imports Canvas course 101 first
    client.post("/api/canvas/courses/101/import", headers=fac, json={})

    r, tok, q = launch(client, platform)
    s = session(r)
    assert s["next"].startswith("/lti/course/101")
    me = client.get("/api/auth/me", headers=s["h"]).json()
    assert me["email"] == "prof.lti@utdallas.edu" and me["role"] == "faculty" and me["sso"]
    page = client.get("/api/lti/course/101", headers=s["h"]).json()
    assert page["set_up"] and page["staff"] and page["course"]["code"] == "BUAN 6320" and page["score_basis"] == "graded work"
    assert {"score", "gaps", "reviewed", "open_decisions"} <= set(page)
    tab = next(b for b in page["builds"] if b["skill"] == "Tableau")
    assert tab["status"] == "covered" and tab["graded_in"] == ["Project 1: Tableau dashboard"]

    # the same launch cannot be replayed
    again = client.post("/api/lti/launch", data={"id_token": tok, "state": q["state"]}, follow_redirects=False)
    assert again.status_code == 400 and "already used" in again.text

    r2, _, _ = launch(client, platform, sub="canvas-student-7", email="stu.lti@utdallas.edu", name="Stu LTI", **{C + "roles": [LEARNER]})
    st = session(r2)
    sp = client.get("/api/lti/course/101", headers=st["h"]).json()
    assert client.get("/api/auth/me", headers=st["h"]).json()["role"] == "student"
    assert not sp["staff"] and "gaps" not in sp and "score" not in sp and sp["my_badges"] == [] and sp["builds"]
    assert client.get("/api/lti/course/999", headers=st["h"]).json() == {"canvas_course_id": "999", "role": "student", "staff": False, "set_up": False}


@pytest.mark.parametrize("case", ["audience", "nonce", "forged", "expired", "version", "custom", "domain", "deployment", "state"])
def test_bad_launches_are_refused(client, platform, monkeypatch, case):
    over = {"sub": f"bad-{case}", "email": f"bad.{case}@utdallas.edu"}
    if case == "audience":
        over["aud"] = "someone-else"
    elif case == "nonce":
        over["nonce"] = "not-the-one-we-sent"
    elif case == "forged":
        over["_key"] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif case == "expired":
        over |= {"exp": int(time.time()) - 600, "iat": int(time.time()) - 900}
    elif case == "version":
        over[C + "version"] = "1.1"
    elif case == "custom":
        over[C + "custom"] = {"canvas_course_id": "$Canvas.course.id"}
    elif case == "domain":
        over["email"] = "someone@gmail.com"
    elif case == "deployment":
        monkeypatch.setattr(get_settings(), "LTI_DEPLOYMENT_IDS", "1:only-this-one")
    if case == "state":
        q = start(client)
        r = client.post("/api/lti/launch", data={"id_token": platform.token(q["nonce"], **over), "state": "forged"}, follow_redirects=False)
    else:
        r, _, _ = launch(client, platform, **over)
    assert r.status_code == 400 and r.headers["content-type"].startswith("text/html"), (case, r.status_code, r.text[:200])


def test_admin_role_is_never_granted_and_login_checks_issuer(client, platform):
    admin_role = "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator"
    r, _, _ = launch(client, platform, sub="canvas-admin-1", email="canvas.admin@utdallas.edu", **{C + "roles": [admin_role]})
    assert client.get("/api/auth/me", headers=session(r)["h"]).json()["role"] == "student"
    bad = client.post("/api/lti/login", data={"iss": "https://evil.example", "login_hint": "x"}, follow_redirects=False)
    assert bad.status_code == 400


def test_in_canvas_pages_may_be_framed_by_canvas_only(client, platform):
    framed = client.get("/lti/course/101")
    assert "frame-ancestors 'self' https://*.instructure.com" in framed.headers.get("content-security-policy", "")
    assert "x-frame-options" not in framed.headers
    assert client.get("/app").headers.get("x-frame-options") == "DENY"
    err = client.post("/api/lti/launch", data={"id_token": "x", "state": "y"})   # launch errors show inside the frame too
    assert err.status_code == 400 and "frame-ancestors" in err.headers.get("content-security-policy", "")


def test_lti_off_by_default(client):
    assert client.post("/api/lti/login", data={"iss": ISS, "login_hint": "x"}).status_code == 404
    assert client.get("/lti/course/1").headers.get("x-frame-options") == "DENY"
