"""Local stand-ins for the university's systems, for demos and development without real credentials.

    python scripts/fake_institution.py            # serves on http://127.0.0.1:8899

Then start CometIQ with:
    SSO_ENABLED=true SSO_ISSUER=http://127.0.0.1:8899/idp SSO_CLIENT_ID=cometiq SSO_CLIENT_SECRET=dev
    CANVAS_BASE_URL=http://127.0.0.1:8899/canvas CANVAS_CLIENT_ID=1 CANVAS_CLIENT_SECRET=dev
    CREDENTIALS_BASE_URL=http://127.0.0.1:8899/badgr CREDENTIALS_TOKEN=dev CREDENTIALS_ISSUER_ID=ISS1

- /idp: an OpenID Connect provider with a "choose who to sign in as" page (RS256-signed ID tokens, PKCE checked).
- /canvas: Canvas OAuth2 and REST endpoints with two demo courses, a syllabus page and graded assignments.
- /badgr: the Canvas Credentials (Badgr v2) endpoints CometIQ uses; see /badgr/_sent for what was received.
Never point a production deployment at this.
"""
import base64
import hashlib
import html
import json
import secrets
import time
from urllib.parse import urlencode

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

BASE = "http://127.0.0.1:8899"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CODES: dict[str, dict] = {}
SENT: dict[str, list] = {"badgeclasses": [], "assertions": [], "revoked": []}
PEOPLE = {
    "faculty": {"sub": "fake-fac-1", "email": "dr.rivera@utdallas.edu", "preferred_username": "mxr190001@utdallas.edu", "name": "Maria Rivera", "roles": ["Faculty"]},
    "student": {"sub": "fake-stu-1", "email": "sam.lee@utdallas.edu", "preferred_username": "sxl220002@utdallas.edu", "name": "Sam Lee", "roles": ["Student"]},
    "staff": {"sub": "fake-adv-1", "email": "a.okafor@utdallas.edu", "preferred_username": "axo150003@utdallas.edu", "name": "Ada Okafor", "roles": ["Staff"]},
}
PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title><style>body{{font-family:system-ui;background:#f1f5f9;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{background:#fff;padding:2rem;border-radius:12px;box-shadow:0 1px 4px #0002;max-width:420px}}button{{display:block;width:100%;margin:.5rem 0;padding:.7rem;border:1px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer;text-align:left;font-size:1rem}}
button:hover{{background:#f8fafc}}small{{color:#475569}}</style></head><body><main><h1 style="font-size:1.25rem">{title}</h1><p><small>Local stand-in for development. Not a real {what}.</small></p>{body}</main></body></html>"""


def jwk():
    return {**json.loads(RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "fake-1", "use": "sig", "alg": "RS256"}


# ── Identity provider ──────────────────────────────────────────────────────────
async def idp_config(_):
    return JSONResponse({"issuer": f"{BASE}/idp", "authorization_endpoint": f"{BASE}/idp/authorize", "token_endpoint": f"{BASE}/idp/token",
                         "jwks_uri": f"{BASE}/idp/keys", "response_types_supported": ["code"], "id_token_signing_alg_values_supported": ["RS256"],
                         "code_challenge_methods_supported": ["S256"]})


async def idp_keys(_):
    return JSONResponse({"keys": [jwk()]})


async def idp_authorize(req: Request):
    q = dict(req.query_params)
    if "who" in q:
        code = secrets.token_urlsafe(16)
        CODES[code] = {"nonce": q["nonce"], "challenge": q["code_challenge"], "claims": PEOPLE[q["who"]], "client_id": q["client_id"]}
        return RedirectResponse(f"{q['redirect_uri']}?{urlencode({'code': code, 'state': q['state']})}", 303)
    buttons = "".join(f'<form method="get"><input type="hidden" name="who" value="{k}">'
                      + "".join(f'<input type="hidden" name="{html.escape(a)}" value="{html.escape(b)}">' for a, b in q.items())
                      + f'<button><b>{html.escape(p["name"])}</b><br><small>{html.escape(p["email"])} · {p["roles"][0]}</small></button></form>'
                      for k, p in PEOPLE.items())
    return HTMLResponse(PAGE.format(title="UTD sign-in (demo)", what="identity provider", body="<p>Sign in as:</p>" + buttons))


async def idp_token(req: Request):
    form = await req.form()
    c = CODES.pop(form.get("code", ""), None)
    pkce = base64.urlsafe_b64encode(hashlib.sha256(str(form.get("code_verifier", "")).encode()).digest()).rstrip(b"=").decode()
    if not c or pkce != c["challenge"]:
        return JSONResponse({"error": "invalid_grant"}, 400)
    now = int(time.time())
    tok = jwt.encode({"iss": f"{BASE}/idp", "aud": c["client_id"], "nonce": c["nonce"], "iat": now, "exp": now + 600, **c["claims"]},
                     KEY, algorithm="RS256", headers={"kid": "fake-1"})
    return JSONResponse({"id_token": tok, "access_token": secrets.token_urlsafe(16), "token_type": "Bearer", "expires_in": 600})


# ── Canvas ─────────────────────────────────────────────────────────────────────
COURSES = {
    "101": {"id": 101, "name": "Database Foundations for Business Analytics", "course_code": "BUAN6320.001.26F", "workflow_state": "available",
            "term": {"name": "2026 Fall"},
            "syllabus_body": "<h2>Course description</h2><p>Relational databases for analytics.</p><h3>Learning objectives</h3><ul><li>Design relational schemas</li>"
                             "<li>Write <b>SQL</b> queries with joins, aggregation and window functions</li><li>Load and clean data with Python</li></ul>"
                             "<h3>Schedule</h3><p>Week 1: Relational modeling</p><p>Week 2: SQL joins lab</p><p>Week 3: Aggregation</p><p>Week 4: Data warehousing</p>"},
    "102": {"id": 102, "name": "Business Analytics with R", "course_code": "BUAN6356.002.26F", "workflow_state": "available", "term": {"name": "2026 Fall"},
            "syllabus_body": "<p>Statistical modeling and data visualization with R and Tableau.</p><p>Week 1: R basics</p><p>Week 2: Regression</p>"},
}
ASSIGNMENTS = {
    "101": [{"id": 11, "name": "Project 1: Sales dashboard in Tableau", "points_possible": 100, "due_at": "2026-10-02T23:59:00Z", "grading_type": "points",
             "published": True, "submission_types": ["online_upload"],
             "description": "<p>Build an interactive Tableau dashboard from the sales warehouse you designed.</p>",
             "rubric": [{"description": "Data preparation", "long_description": "Cleans the extract with Python (pandas)", "points": 30},
                        {"description": "Dashboard design", "long_description": "Clear KPIs and filters in Tableau", "points": 40}]},
            {"id": 12, "name": "Homework 3: Window functions", "points_possible": 50, "due_at": "2026-09-20T23:59:00Z", "grading_type": "points",
             "published": True, "description": "<p>Answer ten questions with SQL window functions.</p>"},
            {"id": 13, "name": "Welcome survey", "points_possible": 0, "grading_type": "not_graded", "published": True, "description": "<p>Tell us about yourself.</p>"}],
    "102": [{"id": 21, "name": "Regression report", "points_possible": 100, "grading_type": "points", "published": True,
             "description": "<p>Fit and interpret a regression model in R.</p>"}],
}


async def canvas_authorize(req: Request):
    q = dict(req.query_params)
    if q.get("approve"):
        return RedirectResponse(f"{q['redirect_uri']}?{urlencode({'code': 'canvas-demo-code', 'state': q['state']})}", 303)
    hidden = "".join(f'<input type="hidden" name="{html.escape(a)}" value="{html.escape(b)}">' for a, b in q.items())
    return HTMLResponse(PAGE.format(title="Canvas: allow CometIQ? (demo)", what="Canvas", body=(
        "<p>CometIQ is requesting access to your courses, syllabus pages and assignments.</p>"
        f'<form method="get"><input type="hidden" name="approve" value="1">{hidden}<button><b>Authorize</b></button></form>')))


async def canvas_token(req: Request):
    if req.method == "DELETE":
        return JSONResponse({})
    form = await req.form()
    if form.get("grant_type") == "refresh_token":
        return JSONResponse({"access_token": "canvas-demo-token", "expires_in": 3600})
    if form.get("code") != "canvas-demo-code":
        return JSONResponse({"error": "invalid_grant"}, 400)
    return JSONResponse({"access_token": "canvas-demo-token", "refresh_token": "canvas-demo-refresh", "expires_in": 3600,
                         "user": {"id": 7, "name": "Maria Rivera"}})


def _canvas_auth(req: Request):
    return req.headers.get("authorization") == "Bearer canvas-demo-token"


async def canvas_courses(req: Request):
    if not _canvas_auth(req):
        return JSONResponse({"errors": [{"message": "Invalid access token."}]}, 401)
    return JSONResponse([{k: v for k, v in c.items() if k != "syllabus_body"} for c in COURSES.values()])


async def canvas_course(req: Request):
    if not _canvas_auth(req):
        return JSONResponse({}, 401)
    c = COURSES.get(req.path_params["cid"])
    return JSONResponse(c) if c else JSONResponse({"errors": [{"message": "not found"}]}, 404)


async def canvas_assignments(req: Request):
    if not _canvas_auth(req):
        return JSONResponse({}, 401)
    return JSONResponse(ASSIGNMENTS.get(req.path_params["cid"], []))


# ── Canvas Credentials (Badgr v2) ──────────────────────────────────────────────
async def badgr_classes(req: Request):
    SENT["badgeclasses"].append(await req.json())
    return JSONResponse({"status": {"success": True}, "result": [{"entityId": f"BC{len(SENT['badgeclasses'])}"}]}, 201)


async def badgr_assertions(req: Request):
    SENT["assertions"].append({**(await req.json()), "badgeclass": req.path_params["eid"]})
    return JSONResponse({"status": {"success": True}, "result": [{"entityId": f"AS{len(SENT['assertions'])}"}]}, 201)


async def badgr_revoke(req: Request):
    SENT["revoked"].append(req.path_params["aid"])
    return JSONResponse({"status": {"success": True}})


async def badgr_sent(_):
    return JSONResponse(SENT)


app = Starlette(routes=[
    Route("/idp/.well-known/openid-configuration", idp_config), Route("/idp/keys", idp_keys), Route("/idp/authorize", idp_authorize),
    Route("/idp/token", idp_token, methods=["POST"]),
    Route("/canvas/login/oauth2/auth", canvas_authorize), Route("/canvas/login/oauth2/token", canvas_token, methods=["POST", "DELETE"]),
    Route("/canvas/api/v1/courses", canvas_courses), Route("/canvas/api/v1/courses/{cid}", canvas_course),
    Route("/canvas/api/v1/courses/{cid}/assignments", canvas_assignments),
    Route("/badgr/v2/issuers/{iid}/badgeclasses", badgr_classes, methods=["POST"]),
    Route("/badgr/v2/badgeclasses/{eid}/assertions", badgr_assertions, methods=["POST"]),
    Route("/badgr/v2/assertions/{aid}", badgr_revoke, methods=["DELETE"]), Route("/badgr/_sent", badgr_sent),
])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
