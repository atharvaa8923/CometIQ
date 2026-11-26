"""CometIQ inside Canvas: an LTI 1.3 tool (1EdTech LTI Core 1.3, Resource Link launch).

Canvas shows "CometIQ skills" in the course menu. Opening it runs the LTI 1.3 launch:
  1. Canvas calls /api/lti/login (third-party initiated login) → CometIQ redirects the browser to Canvas's
     authorization endpoint with a signed state and a fresh nonce.
  2. Canvas posts a signed ID token to /api/lti/launch. CometIQ checks the signature against Canvas's published keys,
     the issuer, audience (our client id), expiry, deployment, message type and version, and that the nonce matches
     the state and has never been used (replay protection, stored in lti_nonces).
  3. The person is signed in to CometIQ (same account matching as single sign-on; Instructor → faculty,
     Learner → student) and lands on the in-Canvas page for that course.

The state is a signed token rather than a cookie: browsers block third-party cookies inside the Canvas iframe.
"""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import jwt
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LtiNonce, User
from . import http

CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
ROLES = {"Instructor": "faculty", "TeachingAssistant": "faculty", "ContentDeveloper": "faculty", "Mentor": "advisor",
         "Learner": "student"}
_jwks: dict[str, tuple[float, dict]] = {}


class LTIError(Exception):
    pass


def enabled() -> bool:
    s = get_settings()
    return bool(s.LTI_ENABLED and s.LTI_CLIENT_ID and s.LTI_ISSUER and s.LTI_AUTH_URL and s.LTI_JWKS_URL)


def app_url() -> str:
    return get_settings().APP_URL.rstrip("/")


def launch_url() -> str:
    return f"{app_url()}/api/lti/launch"


def tool_config() -> dict:
    """Paste-able JSON for a Canvas LTI 1.3 developer key ("Paste JSON" or "Enter URL")."""
    host = urlparse(app_url()).hostname or "localhost"
    return {
        "title": "CometIQ",
        "description": "Skills each course builds, the gaps employers see, and faculty-verified badges.",
        "oidc_initiation_url": f"{app_url()}/api/lti/login",
        "target_link_uri": launch_url(),
        "scopes": [],
        "extensions": [{
            "domain": host, "tool_id": "cometiq", "platform": "canvas.instructure.com", "privacy_level": "public",
            "settings": {"text": "CometIQ skills", "placements": [
                {"placement": "course_navigation", "message_type": "LtiResourceLinkRequest", "text": "CometIQ skills",
                 "target_link_uri": launch_url(), "default": "enabled"}]},
        }],
        "public_jwk_url": f"{app_url()}/api/public/ob/jwks.json",
        "custom_fields": {"canvas_course_id": "$Canvas.course.id", "canvas_user_id": "$Canvas.user.id"},
    }


# ── Step 1: login initiation ───────────────────────────────────────────────────
def login_redirect(params: dict) -> str:
    s = get_settings()
    if params.get("iss") != s.LTI_ISSUER:
        raise LTIError("This launch did not come from the configured Canvas")
    if params.get("client_id") and params["client_id"] != s.LTI_CLIENT_ID:
        raise LTIError("This launch is for a different tool")
    if not params.get("login_hint"):
        raise LTIError("The launch is missing login_hint")
    import secrets

    nonce = secrets.token_urlsafe(24)
    state = jwt.encode({"aud": "cometiq-lti-state", "nonce": nonce, "exp": int(time.time()) + 600,
                        "target": params.get("target_link_uri") or launch_url()}, s.JWT_SECRET, algorithm="HS256")
    q = {"scope": "openid", "response_type": "id_token", "response_mode": "form_post", "prompt": "none",
         "client_id": s.LTI_CLIENT_ID, "redirect_uri": launch_url(), "login_hint": params["login_hint"], "state": state, "nonce": nonce}
    if params.get("lti_message_hint"):
        q["lti_message_hint"] = params["lti_message_hint"]
    return f"{s.LTI_AUTH_URL}?{urlencode(q)}"


# ── Step 2: launch ─────────────────────────────────────────────────────────────
def _keys(refresh: bool = False) -> dict:
    url = get_settings().LTI_JWKS_URL
    hit = _jwks.get(url)
    if hit and hit[0] > time.time() and not refresh:
        return hit[1]
    with http() as c:
        r = c.get(url)
    if r.status_code != 200:
        raise LTIError("Canvas's signing keys are not reachable right now")
    keys = {k.get("kid"): k for k in r.json().get("keys", [])}
    _jwks[url] = (time.time() + 3600, keys)
    return keys


def verify_launch(db: Session, id_token: str, state: str) -> dict:
    s = get_settings()
    try:
        st = jwt.decode(state or "", s.JWT_SECRET, algorithms=["HS256"], audience="cometiq-lti-state")
    except jwt.PyJWTError:
        raise LTIError("This launch expired. Open CometIQ from Canvas again.")
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise LTIError("The launch token is malformed")
    if header.get("alg") != "RS256":
        raise LTIError("The launch token must be signed with RS256")
    jwk = _keys().get(header.get("kid")) or _keys(refresh=True).get(header.get("kid"))
    if not jwk:
        raise LTIError("The launch token is signed with an unknown key")
    try:
        claims = jwt.decode(id_token, jwt.PyJWK(jwk).key, algorithms=["RS256"], audience=s.LTI_CLIENT_ID, issuer=s.LTI_ISSUER,
                            leeway=60, options={"require": ["exp", "iat", "sub", "aud", "iss", "nonce"]})
    except jwt.PyJWTError as e:
        raise LTIError(f"The launch token is not valid ({type(e).__name__})")
    aud = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
    if len(aud) > 1 and claims.get("azp") != s.LTI_CLIENT_ID:
        raise LTIError("The launch token was issued to another tool")
    if claims["nonce"] != st["nonce"]:
        raise LTIError("The launch token does not belong to this launch")
    if claims.get(CLAIM + "version") != "1.3.0" or claims.get(CLAIM + "message_type") != "LtiResourceLinkRequest":
        raise LTIError("Unsupported LTI message")
    deployments = {d.strip() for d in s.LTI_DEPLOYMENT_IDS.split(",") if d.strip()}
    if deployments and claims.get(CLAIM + "deployment_id") not in deployments:
        raise LTIError("This Canvas deployment is not allowed")
    db.execute(delete(LtiNonce).where(LtiNonce.created_at < datetime.now(timezone.utc) - timedelta(days=1)))
    db.add(LtiNonce(nonce=claims["nonce"]))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise LTIError("This launch was already used. Open CometIQ from Canvas again.")
    return claims


def role_of(claims: dict) -> str:
    roles = claims.get(CLAIM + "roles") or []
    found = {ROLES[r.rsplit("#", 1)[-1]] for r in roles if r.rsplit("#", 1)[-1] in ROLES and "/membership" in r}
    return next((r for r in ("faculty", "advisor", "student") if r in found), "student")


def course_of(claims: dict) -> dict:
    ctx = claims.get(CLAIM + "context") or {}
    custom = claims.get(CLAIM + "custom") or {}
    cid = str(custom.get("canvas_course_id") or "").strip()
    if not cid or cid.startswith("$"):
        raise LTIError("Add the custom field canvas_course_id=$Canvas.course.id to the CometIQ developer key")
    return {"canvas_course_id": cid, "label": ctx.get("label"), "title": ctx.get("title")}


def sign_in(db: Session, claims: dict) -> tuple[User, dict]:
    from .accounts import AccountError, link_or_create
    from .sso import domains, institutional

    s = get_settings()
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise LTIError("Canvas did not share an email address: set the developer key's privacy level to Public")
    if not institutional(email):
        raise LTIError(f"Open CometIQ with your {', '.join(sorted(domains()))} Canvas account")
    course = course_of(claims)
    name = claims.get("name") or " ".join(x for x in (claims.get("given_name"), claims.get("family_name")) if x) or email.split("@")[0]
    try:
        user, _ = link_or_create(db, provider=s.LTI_ISSUER, subject=str(claims["sub"]), email=email, name=str(name)[:200],
                                 role=role_of(claims), netid=None, auto_provision=s.LTI_AUTO_PROVISION, action="login.lti")
    except AccountError as e:
        raise LTIError(str(e)) from None
    return user, course
