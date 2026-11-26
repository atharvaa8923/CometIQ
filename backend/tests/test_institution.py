"""Institution integrations against in-process fakes of the real services (no network):
single sign-on (OpenID Connect), Canvas, Canvas Credentials, Open Badges 3.0 + LinkedIn, Handshake."""
import base64
import hashlib
import io
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import func, select

from app import integrations
from app.config import get_settings
from app.db import SessionLocal

ISS = "https://idp.test/tenant/v2.0"


# ── Fakes ──────────────────────────────────────────────────────────────────────
class FakeIdP:
    def __init__(self):
        self.key, self.kid = rsa.generate_private_key(public_exponent=65537, key_size=2048), "idp-key-1"
        self.codes: dict[str, tuple[str, str, dict]] = {}
        self.override: dict = {}
        self.sign_with = None   # another key, to simulate a forged token

    def jwk(self):
        return {**json.loads(RSAAlgorithm.to_jwk(self.key.public_key())), "kid": self.kid, "use": "sig"}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/tenant/v2.0/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISS, "authorization_endpoint": "https://idp.test/tenant/oauth2/v2.0/authorize",
                                             "token_endpoint": "https://idp.test/tenant/oauth2/v2.0/token",
                                             "jwks_uri": "https://idp.test/tenant/discovery/v2.0/keys"})
        if p == "/tenant/discovery/v2.0/keys":
            return httpx.Response(200, json={"keys": [self.jwk()]})
        if p == "/tenant/oauth2/v2.0/token":
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            nonce, challenge, claims = self.codes.pop(form["code"])
            pkce = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
            if pkce != challenge or form["client_id"] != "cometiq-client" or form["client_secret"] != "s3cret":
                return httpx.Response(400, json={"error": "invalid_grant"})
            now = int(time.time())
            body = {"iss": ISS, "aud": "cometiq-client", "nonce": nonce, "iat": now, "exp": now + 300, **claims, **self.override}
            tok = jwt.encode(body, self.sign_with or self.key, algorithm="RS256", headers={"kid": self.override.get("_kid", self.kid)})
            return httpx.Response(200, json={"id_token": tok, "access_token": "at", "token_type": "Bearer"})
        return httpx.Response(404)


class FakeCanvas:
    def __init__(self):
        self.syllabus = ("<h2>BUAN 6320 Database Foundations</h2><p>Learning objectives</p><ul><li>Write <b>SQL</b> queries with joins</li>"
                         "<li>Design relational schemas</li></ul><p>Week 1: Relational modeling</p><p>Week 2: SQL joins lab</p>")
        self.expires_in, self.refreshes, self.revoked = 3600, 0, 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p == "/login/oauth2/token" and req.method == "POST":
            form = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
            if form["grant_type"] == "authorization_code" and form["code"] == "canvas-code":
                return httpx.Response(200, json={"access_token": "AT1", "refresh_token": "RT1", "expires_in": self.expires_in,
                                                 "user": {"id": 42, "name": "Dr. Faculty"}})
            if form["grant_type"] == "refresh_token" and form["refresh_token"] == "RT1":
                self.refreshes += 1
                return httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600})
            return httpx.Response(400, json={"error": "invalid_grant"})
        if p == "/login/oauth2/token" and req.method == "DELETE":
            self.revoked += 1
            return httpx.Response(200, json={})
        if req.headers.get("authorization") not in ("Bearer AT1", "Bearer AT2"):
            return httpx.Response(401, json={"errors": [{"message": "Invalid access token."}]})
        if p == "/api/v1/courses":
            if req.url.params.get("page") == "2":
                return httpx.Response(200, json=[{"id": 202, "name": "Old Seminar", "course_code": "MKT 9999", "workflow_state": "completed",
                                                  "term": {"name": "2025 Spring"}}])
            assert req.url.params.get("enrollment_type") == "teacher"
            return httpx.Response(200, json=[{"id": 101, "name": "Database Foundations", "course_code": "BUAN6320.001.26F",
                                              "workflow_state": "available", "term": {"name": "2026 Fall"}}],
                                  headers={"Link": '<https://canvas.test/api/v1/courses?page=2&per_page=50>; rel="next"'})
        if p == "/api/v1/courses/101":
            return httpx.Response(200, json={"id": 101, "name": "Database Foundations", "course_code": "BUAN6320.001.26F",
                                             "term": {"name": "2026 Fall"}, "syllabus_body": self.syllabus})
        if p == "/api/v1/courses/101/assignments":
            return httpx.Response(200, json=[
                {"id": 1, "name": "Project 1: Tableau dashboard", "points_possible": 100, "due_at": "2026-10-01T23:59:00Z",
                 "grading_type": "points", "published": True, "submission_types": ["online_upload"],
                 "description": "<p>Build an interactive <em>Tableau</em> dashboard from the sales data.</p>",
                 "rubric": [{"description": "Data preparation", "long_description": "Cleans the data with Python (pandas)", "points": 30,
                             "ratings": [{"description": "Full marks", "points": 30}]}]},
                {"id": 2, "name": "Intro survey", "points_possible": 0, "grading_type": "not_graded", "published": True,
                 "description": "<p>Tell us about your Excel experience</p>"},
                {"id": 3, "name": "Draft (unpublished)", "points_possible": 50, "published": False, "description": "<p>Power BI</p>"},
            ])
        return httpx.Response(404, json={"errors": [{"message": "not found"}]})


class FakeBadgr:
    def __init__(self):
        self.classes, self.assertions, self.revoked = [], {}, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.headers.get("authorization") != "Bearer badgr-token":
            return httpx.Response(401)
        p = req.url.path
        if req.method == "POST" and p == "/v2/issuers/ISS1/badgeclasses":
            body = json.loads(req.content)
            assert body["image"].startswith("data:image/svg+xml;base64,") and body["criteriaNarrative"]
            self.classes.append(body)
            return httpx.Response(201, json={"status": {"success": True}, "result": [{"entityId": f"BC{len(self.classes)}"}]})
        if req.method == "POST" and (m := re.fullmatch(r"/v2/badgeclasses/(BC\d+)/assertions", p)):
            body = json.loads(req.content)
            assert body["recipient"]["hashed"] and body["recipient"]["type"] == "email" and body["evidence"][0]["url"]
            aid = f"AS{len(self.assertions) + 1}"
            self.assertions[aid] = {**body, "badgeclass": m.group(1)}
            return httpx.Response(201, json={"status": {"success": True}, "result": [{"entityId": aid}]})
        if req.method == "DELETE" and (m := re.fullmatch(r"/v2/assertions/(AS\d+)", p)):
            self.revoked.append(m.group(1))
            return httpx.Response(200, json={"status": {"success": True}})
        return httpx.Response(404)


@pytest.fixture
def fakes(monkeypatch):
    from app.integrations import sso

    f = {"idp.test": FakeIdP(), "canvas.test": FakeCanvas(), "badgr.test": FakeBadgr(), "handshake.test": None}
    monkeypatch.setattr(integrations, "_transport", httpx.MockTransport(lambda req: f[req.url.host](req)))
    s = get_settings()
    for k, v in {"SSO_ENABLED": True, "SSO_ISSUER": ISS, "SSO_CLIENT_ID": "cometiq-client", "SSO_CLIENT_SECRET": "s3cret",
                 "SSO_ROLE_MAP": "faculty:faculty,staff:advisor,student:student", "SSO_REQUIRED": False,
                 "CANVAS_BASE_URL": "https://canvas.test", "CANVAS_CLIENT_ID": "10000000000001", "CANVAS_CLIENT_SECRET": "canvas-secret",
                 "CREDENTIALS_BASE_URL": "https://badgr.test", "CREDENTIALS_TOKEN": "badgr-token", "CREDENTIALS_ISSUER_ID": "ISS1",
                 "CREDENTIALS_AUTO_SEND": False}.items():
        monkeypatch.setattr(s, k, v)
    sso._discovery.clear()
    sso._jwks.clear()
    yield f
    sso._discovery.clear()
    sso._jwks.clear()


def sso_login(client, idp: FakeIdP, claims: dict, nxt: str = "/gap", state: str | None = None) -> httpx.Response:
    r = client.get(f"/api/auth/sso/login?next={nxt}", follow_redirects=False)
    assert r.status_code == 303, r.text
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    assert r.headers["location"].startswith("https://idp.test/tenant/oauth2/v2.0/authorize?")
    assert q["code_challenge_method"] == "S256" and q["client_id"] == "cometiq-client" and q["redirect_uri"].endswith("/api/auth/sso/callback")
    code = secrets.token_hex(8)
    idp.codes[code] = (q["nonce"], q["code_challenge"], claims)
    return client.get(f"/api/auth/sso/callback?code={code}&state={state or q['state']}", follow_redirects=False)


def token_of(r: httpx.Response) -> dict:
    loc = urlparse(r.headers["location"])
    assert loc.path == "/sso/complete", r.headers["location"]
    frag = {k: v[0] for k, v in parse_qs(loc.fragment).items()}
    return {"Authorization": f"Bearer {frag['token']}", "_next": frag["next"]}


def error_of(r: httpx.Response) -> str:
    loc = urlparse(r.headers["location"])
    assert r.status_code == 303 and loc.path == "/login", r.headers["location"]
    return parse_qs(loc.query)["sso_error"][0]


# ── Single sign-on ─────────────────────────────────────────────────────────────
def test_sso_creates_faculty_account_and_links_identity(client, fakes):
    from app.models import User, UserIdentity

    idp = fakes["idp.test"]
    claims = {"sub": "entra-oid-1", "email": "Jane.Doe@UTDallas.edu", "preferred_username": "JXD190000@utdallas.edu",
              "name": "Jane Doe", "roles": ["Faculty"]}
    h = token_of(sso_login(client, idp, claims))
    assert h.pop("_next") == "/gap"
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email"] == "jane.doe@utdallas.edu" and me["role"] == "faculty" and me["sso"] is True and me["consent_version"] is None
    # same person, email changed at the provider: still matched by the stable subject id
    h2 = token_of(sso_login(client, idp, {**claims, "email": "jane.d@utdallas.edu"}))
    assert client.get("/api/auth/me", headers=h2).json()["id"] == me["id"]
    with SessionLocal() as db:
        ids = list(db.scalars(select(UserIdentity).where(UserIdentity.user_id == me["id"])))
        assert len(ids) == 1 and ids[0].netid == "jxd190000" and ids[0].provider == ISS
        assert db.get(User, me["id"]).password_hash.startswith("!sso:")
    # an SSO account has no CometIQ password: password sign-in fails
    assert client.post("/api/auth/login", json={"email": "jane.doe@utdallas.edu", "password": "!sso:"}).status_code == 401


def test_sso_links_an_existing_account_and_defaults_role(client, fakes):
    r = client.post("/api/auth/register", json={"email": "existing.prof@utdallas.edu", "password": "Existing-Pass-1", "full_name": "Existing Prof",
                                                 "role": "faculty", "join_code": "COMET-UTD", "accept_terms": True})
    uid = r.json()["user"]["id"]
    h = token_of(sso_login(client, fakes["idp.test"], {"sub": "entra-oid-2", "email": "existing.prof@utdallas.edu", "name": "E. Prof"}))
    me = client.get("/api/auth/me", headers=h).json()
    assert me["id"] == uid and me["role"] == "faculty"          # existing role kept, no duplicate account
    new = token_of(sso_login(client, fakes["idp.test"], {"sub": "entra-oid-3", "email": "new.student@utdallas.edu", "name": "New Student"}))
    assert client.get("/api/auth/me", headers=new).json()["role"] == "student"   # no mapped role claim: the default


def test_sso_never_grants_admin(client, fakes, monkeypatch):
    monkeypatch.setattr(get_settings(), "SSO_ROLE_MAP", "it-admins:admin,faculty:faculty")
    h = token_of(sso_login(client, fakes["idp.test"], {"sub": "entra-oid-9", "email": "it.person@utdallas.edu", "name": "IT", "roles": ["it-admins"]}))
    assert client.get("/api/auth/me", headers=h).json()["role"] == "student"


@pytest.mark.parametrize("case", ["state", "nonce", "audience", "expired", "forged", "unknown_kid", "domain"])
def test_sso_rejects_bad_responses(client, fakes, case):
    idp = fakes["idp.test"]
    claims = {"sub": f"bad-{case}", "email": f"bad.{case}@utdallas.edu", "name": "Bad"}
    if case == "nonce":
        idp.override = {"nonce": "something-else"}
    elif case == "audience":
        idp.override = {"aud": "another-app"}
    elif case == "expired":
        idp.override = {"exp": int(time.time()) - 600, "iat": int(time.time()) - 1200}
    elif case == "forged":
        idp.sign_with = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif case == "unknown_kid":
        idp.override = {"_kid": "rotated-away"}
    elif case == "domain":
        claims["email"] = "someone@gmail.com"
    r = sso_login(client, idp, claims, state="tampered-state" if case == "state" else None)
    msg = error_of(r)
    expected = {"state": "did not match", "nonce": "not issued for this sign-in", "audience": "not valid", "expired": "not valid",
                "forged": "not valid", "unknown_kid": "unknown key", "domain": "utdallas.edu"}[case]
    assert expected in msg, msg
    with SessionLocal() as db:
        from app.models import User

        assert not db.scalar(select(User.id).where(User.email == claims["email"]))   # nobody was signed in or created


def test_sso_required_turns_off_passwords_for_institutional_emails(client, fakes, monkeypatch):
    monkeypatch.setattr(get_settings(), "SSO_REQUIRED", True)
    cfg = client.get("/api/auth/public-config").json()["sso"]
    assert cfg == {"enabled": True, "name": "UTD NetID", "required": True, "domains": ["utdallas.edu"]}
    r = client.post("/api/auth/login", json={"email": "existing.prof@utdallas.edu", "password": "Existing-Pass-1"})
    assert r.status_code == 403 and "UTD NetID" in r.json()["detail"]
    assert client.post("/api/auth/register", json={"email": "x.y@utdallas.edu", "password": "Some-Pass-123", "full_name": "X Y", "role": "student",
                                                    "join_code": "COMET-UTD", "accept_terms": True}).status_code == 403
    assert client.post("/api/auth/login", json={"email": "admin@cometiq.app", "password": "CometIQ2026!"}).status_code == 200   # other domains unaffected


def test_sso_user_can_delete_account_without_a_password(client, fakes):
    from app.models import UserIdentity

    h = token_of(sso_login(client, fakes["idp.test"], {"sub": "leaver-1", "email": "leaver@utdallas.edu", "name": "Leaver"}))
    h.pop("_next")
    uid = client.get("/api/auth/me", headers=h).json()["id"]
    assert client.post("/api/privacy/delete-account", headers=h, json={"password": "", "confirm": "DELETE"}).json() == {"deleted": True}
    with SessionLocal() as db:
        assert not db.scalar(select(UserIdentity.id).where(UserIdentity.user_id == uid))


def test_sso_off_by_default(client):
    assert client.get("/api/auth/sso/login", follow_redirects=False).status_code == 404


# ── Canvas ─────────────────────────────────────────────────────────────────────
def _connect_canvas(client, fac):
    url = client.post("/api/canvas/connect", headers=fac).json()["url"]
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert url.startswith("https://canvas.test/login/oauth2/auth?") and q["response_type"] == "code" and "scope" not in q
    r = client.get(f"/api/canvas/callback?code=canvas-code&state={q['state']}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/gap?canvas=connected"), r.headers["location"]


def test_canvas_connect_list_and_import(client, tokens, fakes):
    from app.models import CanvasConnection, CourseAssignment, Syllabus, SyllabusVersion

    fac, canvas = tokens["faculty"], fakes["canvas.test"]
    assert client.get("/api/canvas/status", headers=fac).json()["connected"] is False
    assert client.get("/api/canvas/callback?code=canvas-code&state=forged", follow_redirects=False).headers["location"].count("canvas_error") == 1
    _connect_canvas(client, fac)
    st = client.get("/api/canvas/status", headers=fac).json()
    assert st["connected"] and st["canvas_name"] == "Dr. Faculty"
    with SessionLocal() as db:   # tokens are encrypted at rest
        conn = db.scalars(select(CanvasConnection)).first()
        assert "AT1" not in conn.access_token and "RT1" not in (conn.refresh_token or "")

    courses = client.get("/api/canvas/courses", headers=fac).json()
    assert [c["id"] for c in courses] == ["101", "202"]                         # both pages
    c101 = courses[0]
    assert c101["catalog_code"] == "BUAN 6320" and c101["in_catalog"] and c101["semester"] == "Fall 2026" and not c101["imported_syllabus_id"]

    r = client.post("/api/canvas/courses/101/import", headers=fac, json={}).json()
    assert r["status"] == "done", r
    res = client.get(f"/api/tasks/{r['task_id']}", headers=fac).json()["result"]
    assert res["created"] and res["assignments"] == 2 and res["graded_assignments"] == 1 and res["analysis_id"]
    sid = res["syllabus_id"]
    a = client.get(f"/api/canvas/syllabi/{sid}/assignments", headers=fac).json()
    names = {x["name"]: x for x in a["assignments"]}
    assert set(names) == {"Project 1: Tableau dashboard", "Intro survey"}             # the unpublished one is skipped
    assert {"Tableau", "Python"} <= set(names["Project 1: Tableau dashboard"]["skills"]) and not names["Intro survey"]["graded"]
    assert "Excel" not in a["graded_practice"] and a["graded_practice"]["Tableau"] == ["Project 1: Tableau dashboard"]
    with SessionLocal() as db:   # graded work is part of the analyzed text, so it counts as practice in the report
        text = db.get(Syllabus, sid).raw_text
        assert "GRADED ASSIGNMENTS" in text and "Assignment: Project 1: Tableau dashboard (100 points, due 2026-10-01) (graded)" in text
        assert "Rubric: Data preparation - Cleans the data with Python (pandas)" in text and "Intro survey" not in text
        assert "<li>" not in text and "- Write SQL queries with joins" in text            # Canvas HTML turned into text

    # re-import without changes: no new version, no new analysis
    again = client.get(f"/api/tasks/{client.post('/api/canvas/courses/101/import', headers=fac, json={}).json()['task_id']}", headers=fac).json()["result"]
    assert again["syllabus_id"] == sid and not again["created"] and not again["changed"] and again["analysis_id"] == res["analysis_id"]
    # the instructor edits the syllabus in Canvas: a new version and a new analysis
    canvas.syllabus += "<p>Week 3: Window functions and query tuning</p>"
    third = client.get(f"/api/tasks/{client.post('/api/canvas/courses/101/import', headers=fac, json={}).json()['task_id']}", headers=fac).json()["result"]
    assert third["changed"] and third["analysis_id"] != res["analysis_id"]
    with SessionLocal() as db:
        syl = db.get(Syllabus, sid)
        assert syl.canvas_course_id == "101" and syl.semester == "Fall 2026" and syl.code == "BUAN 6320"
        assert db.scalar(select(func.count()).select_from(SyllabusVersion).where(SyllabusVersion.syllabus_id == sid)) >= 2
        assert db.scalar(select(func.count()).select_from(CourseAssignment).where(CourseAssignment.syllabus_id == sid)) == 2
    assert client.get("/api/canvas/courses", headers=fac).json()[0]["imported_syllabus_id"] == sid


def test_canvas_refreshes_expired_tokens_and_disconnects(client, tokens, fakes):
    from datetime import datetime, timedelta, timezone

    from app.models import CanvasConnection

    fac, canvas = tokens["faculty"], fakes["canvas.test"]
    _connect_canvas(client, fac)
    with SessionLocal() as db:
        for c in db.scalars(select(CanvasConnection)):
            c.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    assert len(client.get("/api/canvas/courses", headers=fac).json()) == 2 and canvas.refreshes == 1
    assert client.delete("/api/canvas/connection", headers=fac).json() == {"connected": False} and canvas.revoked == 1
    assert client.get("/api/canvas/courses", headers=fac).status_code == 400
    assert client.post("/api/canvas/connect", headers=tokens["student"]).status_code == 403


def test_canvas_errors_are_explained(client, tokens, fakes):
    fac = tokens["faculty"]
    _connect_canvas(client, fac)
    r = client.post("/api/canvas/courses/555/import", headers=fac, json={}).json()
    t = client.get(f"/api/tasks/{r['task_id']}", headers=fac).json()
    assert t["status"] == "failed" and t["error"] == "That Canvas course was not found, or you are not a teacher in it"
    assert client.post("/api/canvas/courses/abc/import", headers=fac, json={}).status_code == 400


def test_canvas_off_by_default(client, tokens):
    assert client.get("/api/canvas/status", headers=tokens["faculty"]).json()["configured"] is False
    assert client.post("/api/canvas/connect", headers=tokens["faculty"]).status_code == 404


# ── Badges: Open Badges 3.0, LinkedIn, Canvas Credentials ─────────────────────
def _badge(skill_name="SQL", code="BUAN 6320"):
    from app.models import Course, Skill, SkillBadge, User

    with SessionLocal() as db:
        st = db.scalar(select(User).where(User.email == "student@cometiq.app"))
        course = db.scalar(select(Course).where(Course.org_id == st.org_id, Course.code == code))
        sk = db.scalar(select(Skill).where(Skill.name == skill_name))
        b = db.scalar(select(SkillBadge).where(SkillBadge.student_id == st.id, SkillBadge.skill_id == sk.id, SkillBadge.course_id == course.id))
        if not b:
            b = SkillBadge(org_id=st.org_id, student_id=st.id, skill_id=sk.id, course_id=course.id, course_code=course.code, level="practiced",
                           term="Fall 2025", public_token=secrets.token_urlsafe(18),
                           basis={"faculty": {"syllabus_semester": "Fall 2025"}, "completion": {"verified_at": "2026-01-10T00:00:00+00:00"}})
            db.add(b)
        b.status, b.level, b.public, b.credentials_assertion_id, b.credentials_error = "active", "practiced", False, None, None
        db.commit()
        return b.id, b.public_token


def test_open_badge_credential_verifies_and_reflects_revocation(client, tokens):
    stu = tokens["student"]
    bid, token = _badge("Tableau", "BUAN 6356")
    ob = client.get(f"/api/badges/{bid}/openbadge", headers=stu).json()
    cred, jws = ob["credential"], ob["jwt"]
    assert cred["type"] == ["VerifiableCredential", "OpenBadgeCredential"] and cred["@context"][0] == "https://www.w3.org/ns/credentials/v2"
    assert cred["credentialSubject"]["achievement"]["achievementType"] == "Competency"
    ident = cred["credentialSubject"]["identifier"][0]
    assert ident["hashed"] and re.fullmatch(r"sha256\$[0-9a-f]{64}", ident["identityHash"])
    assert ident["identityHash"] == "sha256$" + hashlib.sha256(("student@cometiq.app" + ident["salt"]).encode()).hexdigest()
    assert "student@cometiq.app" not in json.dumps(cred) and ob["linkedin_url"] is None   # not shared yet: no LinkedIn link
    # the JWT is signed with the published key
    header = jwt.get_unverified_header(jws)
    keys = client.get("/api/public/ob/jwks.json").json()["keys"]
    assert header["alg"] == "RS256" and header["kid"] == keys[0]["kid"] and header["jwk"]["n"] == keys[0]["n"]
    assert jwt.decode(jws, jwt.PyJWK(keys[0]).key, algorithms=["RS256"])["jti"] == cred["id"]
    issuer = client.get(cred["issuer"]["id"].split("testserver")[-1].replace("http://localhost:8000", "")).json()
    assert issuer["type"] == ["Profile"] and issuer["name"]

    ok = client.post("/api/public/ob/verify", json={"credential": jws}).json()
    assert ok["valid"] and all(c["ok"] for c in ok["checks"]) and ok["summary"]["name"].startswith("Tableau")
    head, body, sig = jws.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "==="))
    payload["name"] = "Python (Mastered)"
    tampered = f"{head}.{base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()}.{sig}"
    assert client.post("/api/public/ob/verify", json={"credential": tampered}).json()["valid"] is False
    forged = jwt.encode(payload, rsa.generate_private_key(public_exponent=65537, key_size=2048), algorithm="RS256", headers={"kid": header["kid"]})
    assert client.post("/api/public/ob/verify", json={"credential": forged}).json()["valid"] is False
    assert client.post("/api/public/ob/verify", json={"credential": "not-a-jwt-at-all-really"}).json()["valid"] is False

    assert client.get(f"/api/public/ob/credentials/{token}").status_code == 404          # private until shared
    client.put(f"/api/badges/{bid}/share", headers=stu, json={"public": True})
    shared = client.get(f"/api/badges/{bid}/openbadge", headers=stu).json()
    li = urlparse(shared["linkedin_url"])
    lq = {k: v[0] for k, v in parse_qs(li.query).items()}
    assert li.netloc == "www.linkedin.com" and lq["startTask"] == "CERTIFICATION_NAME" and lq["certUrl"].endswith(f"/badge/{token}")
    assert client.get(f"/api/public/ob/credentials/{token}").json()["status"] == "active"
    f = client.get(f"/api/badges/{bid}/openbadge.jwt", headers=stu)
    assert f.headers["content-type"].startswith("application/vc+jwt") and f.text.count(".") == 2

    client.post(f"/api/badges/{bid}/revoke", headers=tokens["admin"], json={"reason": "Completion record was entered in error."})
    after = client.post("/api/public/ob/verify", json={"credential": jws}).json()
    assert after["valid"] is False and any(c["check"] == "status" and not c["ok"] for c in after["checks"])
    assert client.get(f"/api/badges/{bid}/openbadge", headers=stu).status_code == 400
    assert client.get(f"/api/badges/{bid}/openbadge", headers=tokens["advisor"]).status_code == 403


def test_badges_go_to_canvas_credentials(client, tokens, fakes, monkeypatch):
    from app.models import SkillBadge

    stu, adm, badgr = tokens["student"], tokens["admin"], fakes["badgr.test"]
    bid, _ = _badge("SQL", "BUAN 6320")
    r = client.post(f"/api/badges/{bid}/send-to-canvas", headers=stu)
    assert r.status_code == 400 and "Share the badge first" in r.json()["detail"]         # only shared badges leave CometIQ
    monkeypatch.setattr(get_settings(), "CREDENTIALS_AUTO_SEND", True)
    client.put(f"/api/badges/{bid}/share", headers=stu, json={"public": True})             # sharing sends it automatically
    assert len(badgr.assertions) == 1 and len(badgr.classes) == 1
    a = next(iter(badgr.assertions.values()))
    assert a["recipient"]["identity"] == "student@cometiq.app" and a["badgeclass"] == "BC1"
    mine = {b["id"]: b for b in client.get("/api/badges/mine", headers=stu).json()["badges"]}
    assert mine[bid]["in_canvas"] and not mine[bid]["canvas_error"]
    # sending again does nothing; a second badge for the same skill and level reuses the badge class
    client.post(f"/api/badges/{bid}/send-to-canvas", headers=stu)
    bid2, _ = _badge("SQL", "BUAN 6356")
    client.put(f"/api/badges/{bid2}/share", headers=stu, json={"public": True})
    assert len(badgr.assertions) == 2 and len(badgr.classes) == 1
    st = client.get("/api/admin/integrations", headers=adm).json()["institution"]["credentials"]
    assert st["enabled"] and st["sent"] >= 2
    # revoking in CometIQ revokes it in Canvas Credentials
    client.post(f"/api/badges/{bid2}/revoke", headers=adm, json={"reason": "Completion record was entered in error."})
    assert badgr.revoked == ["AS2"]
    # errors are recorded on the badge, not lost
    monkeypatch.setattr(get_settings(), "CREDENTIALS_TOKEN", "wrong")
    bid3, _ = _badge("Python", "BUAN 6356")
    client.put(f"/api/badges/{bid3}/share", headers=stu, json={"public": True})
    with SessionLocal() as db:
        assert "rejected the API token" in db.get(SkillBadge, bid3).credentials_error


# ── Handshake ──────────────────────────────────────────────────────────────────
CSV = """Job ID,Job Title,Employer,Location(s),Job Type,Posted Date,Expiration Date,Description
HS-1,Data Analyst Intern,Acme Analytics,"Dallas, TX",Internship,2026-11-01,2099-01-01,"Build SQL queries, Python scripts and Tableau dashboards."
HS-2,Financial Analyst,Lone Star Bank,"Richardson, TX",Full-Time,11/02/2026,,Excel financial modeling and forecasting.
HS-3,Old Role,Gone LLC,Remote,Full-Time,2026-01-01,2026-02-01,An expired posting.
,Row without an id,,,,,,
"""


def _upload(client, h, name, data: bytes):
    return client.post("/api/admin/handshake/import", headers=h, files={"file": (name, io.BytesIO(data), "application/octet-stream")})


def test_handshake_export_import_is_a_snapshot(client, tokens):
    from app.models import Job

    adm = tokens["admin"]
    r = _upload(client, adm, "handshake_jobs.csv", CSV.encode()).json()
    assert (r["added"], r["expired"], r["skipped"], r["closed_missing"]) == (2, 1, 1, 0), r
    with SessionLocal() as db:
        j = db.scalar(select(Job).where(Job.source == "handshake", Job.external_id == "HS-1"))
        assert j.is_open and j.employment_type == "Internship" and j.company == "Acme Analytics"
        assert j.url == "https://app.joinhandshake.com/jobs/HS-1" and {"SQL", "Python", "Tableau"} <= {s.skill.name for s in j.skills}
        assert db.scalar(select(Job).where(Job.external_id == "HS-2")).posted_at.month == 11
    # next export: HS-2 is gone and HS-1 was retitled
    r2 = _upload(client, adm, "jobs.csv", CSV.replace("Data Analyst Intern", "Data Analytics Intern").replace(
        'HS-2,Financial Analyst,Lone Star Bank,"Richardson, TX",Full-Time,11/02/2026,,Excel financial modeling and forecasting.\n', "").encode()).json()
    assert r2["updated"] == 1 and r2["closed_missing"] == 1 and r2["added"] == 0
    # HS-2 is back, from an Excel export
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Job ID", "Job Title", "Employer", "Job Type", "Expiration Date"])
    ws.append(["HS-1", "Data Analytics Intern", "Acme Analytics", "Internship", "2099-01-01"])
    ws.append(["HS-2", "Financial Analyst", "Lone Star Bank", "Full-Time", None])
    buf = io.BytesIO()
    wb.save(buf)
    r3 = _upload(client, adm, "jobs.xlsx", buf.getvalue()).json()
    assert r3["reopened"] == 1 and r3["open_now"] == 2
    st = client.get("/api/admin/integrations", headers=adm).json()["institution"]["handshake"]
    assert st["open_postings"] == 2 and st["closed_postings"] == 0   # HS-3 had expired before the first import


def test_handshake_rejects_unusable_files(client, tokens):
    adm = tokens["admin"]
    r = _upload(client, adm, "jobs.csv", b"Name,Company\nX,Y\n")
    assert r.status_code == 400 and "Job ID" in r.json()["detail"]
    assert _upload(client, adm, "jobs.pdf", b"%PDF").status_code == 400
    assert _upload(client, tokens["faculty"], "jobs.csv", CSV.encode()).status_code == 403


def test_handshake_feed_pull(client, fakes, monkeypatch):
    from app.integrations import handshake

    seen = {}

    def feed(req):
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"jobs": [{"id": "HS-90", "title": "Supply Chain Analyst", "employer_name": "Freight Co",
                                                   "job_type": "Full-Time", "description": "Excel and SQL"}]})

    fakes["handshake.test"] = feed
    monkeypatch.setattr(get_settings(), "HANDSHAKE_FEED_URL", "https://handshake.test/export")
    monkeypatch.setattr(get_settings(), "HANDSHAKE_FEED_TOKEN", "feed-token")
    with SessionLocal() as db:
        r = handshake.pull_feed(db, handshake.home_org_id(db))
    assert r["in_file"] == 1 and seen["auth"] == "Bearer feed-token"
