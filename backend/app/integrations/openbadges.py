"""Open Badges 3.0: each faculty-verified badge as a signed OpenBadgeCredential that anyone can verify.

- Data model: 1EdTech Open Badges 3.0 (W3C Verifiable Credentials 2.0), `OpenBadgeCredential` with an `Achievement`.
- Proof: VC-JWT (JOSE, RS256). The JWT header carries the key id and the public key; the institution's keys are also
  published at /api/public/ob/jwks.json and the issuer profile at /api/public/ob/issuers/<org>.
- Privacy: the student is identified by a salted SHA-256 hash of their email, as the standard recommends; the
  credential is public only after the student shares the badge.
- Revocation: verification checks the badge's current status, so a revoked badge fails verification at once.
"""
import base64
import hashlib
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from ..config import get_settings

CONTEXT = ["https://www.w3.org/ns/credentials/v2", "https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json"]
KEY_FILE = Path(__file__).resolve().parents[2] / ".keys" / "ob_signing_key.pem"
LEVEL_VERB = {"practiced": "practice", "mastered": "master"}


class Unavailable(Exception):
    pass


def base() -> str:
    return get_settings().APP_URL.rstrip("/")


# ── Signing key ────────────────────────────────────────────────────────────────
def _load_pem() -> bytes:
    s = get_settings()
    if s.OB_SIGNING_KEY.strip():
        return s.OB_SIGNING_KEY.replace("\\n", "\n").encode()
    if s.OB_SIGNING_KEY_FILE:
        return Path(s.OB_SIGNING_KEY_FILE).read_bytes()
    if s.ENV == "production":
        raise Unavailable("Set OB_SIGNING_KEY or OB_SIGNING_KEY_FILE to issue Open Badges")
    if not KEY_FILE.exists():   # development: create a key once (exclusive create, safe with several workers)
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        try:
            fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
        except FileExistsError:
            pass
    return KEY_FILE.read_bytes()


@lru_cache(maxsize=1)
def signing_key():
    key = serialization.load_pem_private_key(_load_pem(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise Unavailable("The Open Badges signing key must be an RSA key of at least 2048 bits")
    return key


def public_jwk() -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(signing_key().public_key()))
    # RFC 7638 thumbprint as the key id
    thumb = json.dumps({k: jwk[k] for k in ("e", "kty", "n")}, separators=(",", ":"), sort_keys=True).encode()
    kid = base64.urlsafe_b64encode(hashlib.sha256(thumb).digest()).rstrip(b"=").decode()
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


def jwks() -> dict:
    return {"keys": [public_jwk()]}


# ── Documents ──────────────────────────────────────────────────────────────────
def issuer(org) -> dict:
    s = get_settings()
    d = {"id": f"{base()}/api/public/ob/issuers/{org.id}", "type": ["Profile"], "name": org.name, "url": base()}
    if s.LINKEDIN_ORG_ID:
        d["otherIdentifier"] = [{"type": "IdentifierEntry", "identifier": s.LINKEDIN_ORG_ID, "identifierType": "identifier"}]
    return d


def achievement(org, skill, level: str) -> dict:
    verb = LEVEL_VERB.get(level, level)
    return {
        "id": f"{base()}/api/public/ob/achievements/{org.id}/{skill.id}/{level}",
        "type": ["Achievement"],
        "achievementType": "Competency",
        "name": f"{skill.name} ({level.capitalize()})",
        "description": f"Completed a course at {org.name} in which faculty confirmed that students {verb} {skill.name}.",
        "criteria": {"narrative": (f"Complete a course whose faculty confirmed, after reviewing the syllabus, that students {verb} "
                                   f"{skill.name}; the completion is verified by an advisor or registrar.")},
        "tag": [skill.category, level],
        "creator": issuer(org),
    }


def credential(badge, org, student) -> dict:
    salt = hashlib.sha256(f"{badge.public_token}:{badge.id}".encode()).hexdigest()[:16]
    f, c = (badge.basis or {}).get("faculty", {}), (badge.basis or {}).get("completion", {})
    verify = f"{base()}/badge/{badge.public_token}"
    narrative = (f"{student.full_name} completed {badge.course_code}" + (f" ({badge.term})" if badge.term else "")
                 + f". Faculty confirmed students {LEVEL_VERB.get(badge.level, badge.level)} {badge.skill.name} in this course"
                 + (f" (syllabus {f['syllabus_semester']})" if f.get("syllabus_semester") else "")
                 + (f"; completion verified {str(c.get('verified_at'))[:10]}." if c.get("verified_at") else "."))
    if badge.partner:
        narrative += f" Earned through a project sponsored by {badge.partner}."
    return {
        "@context": CONTEXT,
        "id": f"{base()}/api/public/ob/credentials/{badge.public_token}",
        "type": ["VerifiableCredential", "OpenBadgeCredential"],
        "issuer": issuer(org),
        "validFrom": badge.issued_at.isoformat().replace("+00:00", "Z") if badge.issued_at.tzinfo else badge.issued_at.isoformat() + "Z",
        "name": f"{badge.skill.name} ({badge.level.capitalize()}), {badge.course_code}",
        "credentialSubject": {
            "type": ["AchievementSubject"],
            "identifier": [{"type": "IdentityObject", "identityType": "emailAddress", "hashed": True, "salt": salt,
                            "identityHash": "sha256$" + hashlib.sha256((student.email.lower() + salt).encode()).hexdigest()}],
            "achievement": achievement(org, badge.skill, badge.level),
        },
        "evidence": [{"id": verify, "type": ["Evidence"], "name": f"{badge.course_code} completion", "narrative": narrative}],
    }


def sign(cred: dict) -> str:
    jwk = public_jwk()
    now = int(time.time())
    payload = {**cred, "iss": cred["issuer"]["id"], "jti": cred["id"], "sub": cred["credentialSubject"]["identifier"][0]["identityHash"],
               "nbf": min(now, int(_ts(cred["validFrom"]))), "iat": now}
    header = {"kid": jwk["kid"], "typ": "JWT", "jwk": {k: jwk[k] for k in ("kty", "n", "e", "kid", "alg", "use")}}
    return jwt.encode(payload, signing_key(), algorithm="RS256", headers=header)


def _ts(iso: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def verify(token: str) -> dict:
    """Signature, issuer key and structure. The caller adds the badge's current status."""
    checks = []
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return {"valid": False, "checks": [{"check": "format", "ok": False, "detail": "Not a JWT"}]}
    ours = public_jwk()
    trusted = header.get("kid") == ours["kid"]
    checks.append({"check": "issuer key", "ok": trusted, "detail": "Signed with this institution's published key" if trusted
                   else "Not signed with a key this institution publishes"})
    if not trusted:
        return {"valid": False, "checks": checks}
    try:
        payload = jwt.decode(token, signing_key().public_key(), algorithms=["RS256"], options={"verify_aud": False})
        checks.append({"check": "signature", "ok": True, "detail": "RS256 signature is valid"})
    except jwt.PyJWTError as e:
        checks.append({"check": "signature", "ok": False, "detail": f"Invalid signature ({type(e).__name__})"})
        return {"valid": False, "checks": checks}
    shape = "OpenBadgeCredential" in payload.get("type", []) and payload.get("@context", [])[:1] == CONTEXT[:1]
    checks.append({"check": "Open Badges 3.0", "ok": shape, "detail": "OpenBadgeCredential with the VC 2.0 context" if shape else "Not an OpenBadgeCredential"})
    return {"valid": all(c["ok"] for c in checks), "checks": checks, "credential": payload}


def linkedin_url(badge, org) -> str:
    """LinkedIn's "Add to profile" form, prefilled (https://addtoprofile.linkedin.com). No API access needed."""
    s = get_settings()
    q = {"startTask": "CERTIFICATION_NAME", "name": f"{badge.skill.name} ({badge.level.capitalize()}), faculty-verified",
         "issueYear": badge.issued_at.year, "issueMonth": badge.issued_at.month,
         "certUrl": f"{base()}/badge/{badge.public_token}", "certId": badge.public_token}
    q |= {"organizationId": s.LINKEDIN_ORG_ID} if s.LINKEDIN_ORG_ID else {"organizationName": org.name}
    return "https://www.linkedin.com/profile/add?" + urlencode(q)


def status() -> dict:
    try:
        return {"enabled": True, "kid": public_jwk()["kid"],
                "source": "OB_SIGNING_KEY" if get_settings().OB_SIGNING_KEY.strip() else
                          "OB_SIGNING_KEY_FILE" if get_settings().OB_SIGNING_KEY_FILE else "development key (backend/.keys)"}
    except Unavailable as e:
        return {"enabled": False, "detail": str(e)}
