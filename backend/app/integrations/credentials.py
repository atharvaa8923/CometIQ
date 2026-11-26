"""Canvas Credentials (formerly Badgr): send faculty-verified badges back into Canvas, where students see them in their
Backpack and can share them from Canvas.

Badgr API v2 (https://api.badgr.io/docs/v2/): one badge class per skill and level, created on first use, then an
assertion per student, addressed to the student's hashed email. Only badges the student chose to share are sent; a
revoked badge's assertion is revoked too.
"""
import base64
from datetime import datetime, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CredentialBadgeClass, Organization, SkillBadge, User
from . import http


class CredentialsError(Exception):
    pass


def enabled() -> bool:
    s = get_settings()
    return bool(s.CREDENTIALS_TOKEN and s.CREDENTIALS_ISSUER_ID)


def _call(method: str, path: str, json: dict | None = None) -> dict:
    s = get_settings()
    with http() as c:
        r = c.request(method, f"{s.CREDENTIALS_BASE_URL.rstrip('/')}{path}", json=json,
                      headers={"Authorization": f"Bearer {s.CREDENTIALS_TOKEN}", "Accept": "application/json"})
    if r.status_code == 401:
        raise CredentialsError("Canvas Credentials rejected the API token")
    if r.status_code >= 400:
        detail = ""
        try:
            detail = str(r.json().get("status", {}).get("description") or r.json().get("fieldErrors") or "")[:200]
        except ValueError:
            pass
        raise CredentialsError(f"Canvas Credentials returned {r.status_code} {detail}".strip())
    return r.json() if r.content else {}


def _image(skill: str, level: str) -> str:
    color = "#0f766e" if level == "mastered" else "#c2410c"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">'
           f'<circle cx="200" cy="200" r="190" fill="{color}"/><circle cx="200" cy="200" r="160" fill="#fff"/>'
           f'<text x="200" y="185" font-family="Arial" font-size="34" font-weight="700" text-anchor="middle" fill="{color}">{escape(skill[:22])}</text>'
           f'<text x="200" y="235" font-family="Arial" font-size="24" text-anchor="middle" fill="#334155">{level.capitalize()}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def badge_class(db: Session, org: Organization, badge: SkillBadge) -> str:
    row = db.scalar(select(CredentialBadgeClass).where(CredentialBadgeClass.org_id == org.id, CredentialBadgeClass.skill_id == badge.skill_id,
                                                       CredentialBadgeClass.level == badge.level))
    if row:
        return row.entity_id
    from .openbadges import achievement

    a = achievement(org, badge.skill, badge.level)
    res = _call("POST", f"/v2/issuers/{get_settings().CREDENTIALS_ISSUER_ID}/badgeclasses", {
        "name": a["name"][:255], "description": a["description"], "criteriaNarrative": a["criteria"]["narrative"],
        "criteriaUrl": a["id"], "image": _image(badge.skill.name, badge.level), "tags": [t for t in a["tag"] if t]})
    eid = (res.get("result") or [{}])[0].get("entityId")
    if not eid:
        raise CredentialsError("Canvas Credentials did not return the new badge class")
    db.add(CredentialBadgeClass(org_id=org.id, skill_id=badge.skill_id, level=badge.level, entity_id=eid))
    db.flush()
    return eid


def send(db: Session, badge: SkillBadge) -> str:
    if badge.credentials_assertion_id:
        return badge.credentials_assertion_id
    if badge.status != "active" or not badge.public:
        raise CredentialsError("Only active badges the student shared are sent")
    org, student = db.get(Organization, badge.org_id), db.get(User, badge.student_id)
    eid = badge_class(db, org, badge)
    from .openbadges import base

    verify = f"{base()}/badge/{badge.public_token}"
    res = _call("POST", f"/v2/badgeclasses/{eid}/assertions", {
        "recipient": {"identity": student.email, "type": "email", "hashed": True},
        "issuedOn": badge.issued_at.astimezone(timezone.utc).isoformat() if badge.issued_at.tzinfo else badge.issued_at.isoformat() + "Z",
        "narrative": f"Completed {badge.course_code}" + (f" ({badge.term})" if badge.term else "") + "; verified by CometIQ.",
        "evidence": [{"url": verify, "narrative": f"Faculty-verified {badge.skill.name} ({badge.level}) in {badge.course_code}"}],
        "notify": True})
    aid = (res.get("result") or [{}])[0].get("entityId")
    if not aid:
        raise CredentialsError("Canvas Credentials did not return the assertion")
    badge.credentials_assertion_id, badge.credentials_sent_at, badge.credentials_error = aid, datetime.now(timezone.utc), None
    return aid


def revoke_assertion(assertion_id: str, reason: str) -> None:
    _call("DELETE", f"/v2/assertions/{assertion_id}", {"revocation_reason": reason[:255]})


def send_many(db: Session, badges: list[SkillBadge]) -> dict:
    sent = failed = 0
    for b in badges:
        try:
            send(db, b)
            sent += 1
        except CredentialsError as e:
            b.credentials_error = str(e)[:500]
            failed += 1
        db.commit()
    return {"sent": sent, "failed": failed}
