"""Single sign-on with OpenID Connect (authorization code flow + PKCE).

Works with Microsoft Entra ID (issuer https://login.microsoftonline.com/<tenant>/v2.0) and with a Shibboleth IdP that has
the OIDC plugin. The browser is sent to the identity provider; it comes back to /api/auth/sso/callback with a code, which
the server exchanges for a signed ID token. The token's signature (provider keys from its JWKS), issuer, audience,
expiry and nonce are checked before anyone is signed in.

The state, nonce and PKCE verifier travel in a short-lived signed cookie, so any app instance can finish a sign-in.
Accounts are matched by the provider's stable subject id, then by institutional email, and created on first sign-in
(role from the provider's affiliation/role claim). An existing account's role is not changed by SSO: admins manage roles.
"""
import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Organization, StudentProfile, User, UserIdentity
from . import http

COOKIE = "cometiq_sso"
STATE_TTL_S = 600
ROLE_PRIORITY = ("faculty", "advisor", "student")   # admin is never granted by SSO: admins assign it in CometIQ
_discovery: dict[str, tuple[float, dict]] = {}
_jwks: dict[str, tuple[float, dict]] = {}


class SSOError(Exception):
    """Shown to the person on the sign-in page."""


def enabled() -> bool:
    s = get_settings()
    return bool(s.SSO_ENABLED and s.SSO_ISSUER and s.SSO_CLIENT_ID)


def redirect_uri() -> str:
    return f"{get_settings().APP_URL.rstrip('/')}/api/auth/sso/callback"


def domains() -> set[str]:
    return {d.strip().lower().lstrip("@") for d in get_settings().SSO_ALLOWED_DOMAINS.split(",") if d.strip()}


def institutional(email: str) -> bool:
    return "@" in email and email.rsplit("@", 1)[1].lower() in domains()


def discovery() -> dict:
    iss = get_settings().SSO_ISSUER.rstrip("/")
    hit = _discovery.get(iss)
    if hit and hit[0] > time.time():
        return hit[1]
    with http() as c:
        r = c.get(f"{iss}/.well-known/openid-configuration")
    if r.status_code != 200:
        raise SSOError("The sign-in service is not reachable right now. Try again in a few minutes.")
    doc = r.json()
    for k in ("authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"):
        if not doc.get(k):
            raise SSOError(f"The identity provider's configuration is missing {k}")
    _discovery[iss] = (time.time() + 3600, doc)
    return doc


def _keys(uri: str, refresh: bool = False) -> dict:
    hit = _jwks.get(uri)
    if hit and hit[0] > time.time() and not refresh:
        return hit[1]
    with http() as c:
        r = c.get(uri)
    r.raise_for_status()
    keys = {k.get("kid"): k for k in r.json().get("keys", [])}
    _jwks[uri] = (time.time() + 3600, keys)
    return keys


# ── Step 1: send the browser to the identity provider ─────────────────────────
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def safe_next(nxt: str | None) -> str:
    return nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt else "/app"


def start(nxt: str | None) -> tuple[str, str]:
    """Returns (provider URL to redirect to, signed state cookie)."""
    s, doc = get_settings(), discovery()
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    cookie = jwt.encode({"aud": "cometiq-sso-state", "exp": int(time.time()) + STATE_TTL_S, "state": state, "nonce": nonce,
                         "verifier": verifier, "next": safe_next(nxt)}, s.JWT_SECRET, algorithm="HS256")
    params = {"response_type": "code", "client_id": s.SSO_CLIENT_ID, "redirect_uri": redirect_uri(), "scope": s.SSO_SCOPES,
              "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{doc['authorization_endpoint']}?{urlencode(params)}", cookie


# ── Step 2: the provider sends the browser back with a code ───────────────────
def read_state(cookie: str | None, state: str | None) -> dict:
    if not cookie:
        raise SSOError("Your sign-in session expired. Start again.")
    try:
        data = jwt.decode(cookie, get_settings().JWT_SECRET, algorithms=["HS256"], audience="cometiq-sso-state")
    except jwt.PyJWTError:
        raise SSOError("Your sign-in session expired. Start again.")
    if not state or not secrets.compare_digest(data["state"], state):
        raise SSOError("The sign-in response did not match this browser. Start again.")
    return data


def exchange(code: str, verifier: str) -> dict:
    s, doc = get_settings(), discovery()
    with http() as c:
        r = c.post(doc["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
                                                "client_id": s.SSO_CLIENT_ID, "client_secret": s.SSO_CLIENT_SECRET,
                                                "code_verifier": verifier}, headers={"Accept": "application/json"})
    if r.status_code != 200 or "id_token" not in r.json():
        raise SSOError("The sign-in service did not accept the response. Start again.")
    return r.json()


def verify_id_token(id_token: str, nonce: str) -> dict:
    s, doc = get_settings(), discovery()
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise SSOError("The sign-in token is malformed")
    if header.get("alg") not in ("RS256", "RS384", "RS512", "PS256", "ES256", "ES384"):
        raise SSOError("The sign-in token uses an unsupported signature")
    keys = _keys(doc["jwks_uri"])
    jwk = keys.get(header.get("kid")) or _keys(doc["jwks_uri"], refresh=True).get(header.get("kid"))   # provider rotated keys
    if not jwk:
        raise SSOError("The sign-in token is signed with an unknown key")
    try:
        claims = jwt.decode(id_token, jwt.PyJWK(jwk).key, algorithms=[header["alg"]], audience=s.SSO_CLIENT_ID,
                            issuer=doc["issuer"], leeway=60, options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.PyJWTError as e:
        raise SSOError(f"The sign-in token is not valid ({type(e).__name__})")
    if not claims.get("nonce") or not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise SSOError("The sign-in token was not issued for this sign-in. Start again.")
    return claims


# ── Step 3: find or create the account ────────────────────────────────────────
def profile(claims: dict) -> dict:
    s = get_settings()
    email = next((v for v in (claims.get("email"), claims.get("upn"), claims.get("preferred_username"))
                  if isinstance(v, str) and "@" in v), None)
    if not email:
        raise SSOError("Your institution did not share an email address with CometIQ")
    email = email.strip().lower()
    raw_netid = str(claims.get(s.SSO_NETID_CLAIM) or email)
    name = claims.get("name") or " ".join(x for x in (claims.get("given_name"), claims.get("family_name")) if x) or email.split("@")[0]
    values = claims.get(s.SSO_ROLE_CLAIM) or []
    values = [values] if isinstance(values, str) else list(values)
    mapping = {}
    for pair in s.SSO_ROLE_MAP.split(","):
        if ":" in pair:
            k, v = pair.split(":", 1)
            mapping[k.strip().lower()] = v.strip()
    mapped = {mapping[str(v).strip().lower()] for v in values if str(v).strip().lower() in mapping}
    default = s.SSO_DEFAULT_ROLE if s.SSO_DEFAULT_ROLE in ROLE_PRIORITY else "student"
    role = next((r for r in ROLE_PRIORITY if r in mapped), default)
    return {"email": email, "netid": raw_netid.split("@")[0].lower()[:80], "name": str(name)[:200], "role": role,
            "affiliations": [str(v) for v in values][:10]}


def _org(db: Session) -> Organization:
    slug = get_settings().SSO_ORG_SLUG
    org = db.scalar(select(Organization).where(Organization.slug == slug)) if slug else None
    org = org or db.scalar(select(Organization).order_by(Organization.created_at))
    if not org:
        raise SSOError("CometIQ is not set up yet")
    return org


def sign_in(db: Session, claims: dict) -> tuple[User, bool]:
    """Returns (user, created)."""
    from ..routers.auth import _role_allowed
    from ..security import audit, hash_password

    s, issuer = get_settings(), discovery()["issuer"]
    p = profile(claims)
    if not institutional(p["email"]):
        raise SSOError(f"Sign in with your {', '.join(sorted(domains()))} account")
    ident = db.scalar(select(UserIdentity).where(UserIdentity.provider == issuer, UserIdentity.subject == str(claims["sub"])))
    user = db.get(User, ident.user_id) if ident else None
    created = False
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == p["email"]))
    if user is None:
        if not s.SSO_AUTO_PROVISION:
            raise SSOError("You don't have a CometIQ account yet. Ask your administrator to add you.")
        if not _role_allowed(p["role"]):
            raise SSOError("This CometIQ pilot is not open to your role yet")
        user = User(org_id=_org(db).id, email=p["email"], full_name=p["name"], role=p["role"],
                    password_hash="!sso:" + hash_password(secrets.token_urlsafe(24)))   # no usable password
        db.add(user)
        db.flush()
        if user.role == "student":
            db.add(StudentProfile(user_id=user.id))
        created = True
    if not user.is_active:
        raise SSOError("This account is disabled")
    if not _role_allowed(user.role):
        raise SSOError("This CometIQ pilot is currently open to faculty only")
    now = datetime.now(timezone.utc)
    if ident is None:
        ident = UserIdentity(user_id=user.id, provider=issuer, subject=str(claims["sub"]))
        db.add(ident)
    ident.netid, ident.email, ident.last_login_at = p["netid"], p["email"], now
    audit(db, user, "login.sso", created=created, netid=p["netid"])
    return user, created
