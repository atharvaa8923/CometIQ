"""Faculty-verified skill badges: students see and share them; anyone with a shared link can verify one."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Course, Organization, SkillBadge, User
from ..security import audit, current_user, require_roles
from ..services import badges as badgesvc

router = APIRouter(prefix="/api/badges", tags=["badges"])
public = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/mine")
def mine(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    badgesvc.sync(db, user.org_id, user.id)
    db.commit()
    rows = [badgesvc.out(b) for b in db.scalars(select(SkillBadge).where(SkillBadge.student_id == user.id).order_by(SkillBadge.issued_at.desc()))]
    # completed courses that would earn badges once the completion is verified
    basis = badgesvc.faculty_basis(db, user.org_id)
    verified = {c["course_id"] for c in badgesvc.verified_completions(db, user.org_id, user.id)}
    from ..models import StudentCourse

    pending = []
    for sc in db.scalars(select(StudentCourse).where(StudentCourse.user_id == user.id, StudentCourse.status == "completed")):
        if sc.course_id not in verified and basis.get(sc.course_id):
            c = db.get(Course, sc.course_id)
            from ..models import Skill

            names = [s.name for s in db.scalars(select(Skill).where(Skill.id.in_(list(basis[sc.course_id]))))]
            pending.append({"course_id": c.id, "course_code": c.code, "course_title": c.title, "skills": sorted(names)})
    from ..integrations import credentials

    return {"badges": rows, "pending": pending, "canvas_credentials": credentials.enabled()}


class ShareIn(BaseModel):
    public: bool


@router.put("/{bid}/share")
def share(bid: str, body: ShareIn, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    b = db.get(SkillBadge, bid)
    if not b or b.student_id != user.id:
        raise HTTPException(404, "Badge not found")
    b.public = body.public
    db.commit()
    from ..config import get_settings
    from ..integrations import credentials
    from ..services import tasks

    if b.public and credentials.enabled() and get_settings().CREDENTIALS_AUTO_SEND and not b.credentials_assertion_id:
        tasks.enqueue(db, "credentials.send", {"badge_ids": [b.id]}, b.org_id, user.id)
    return badgesvc.out(b)


@router.post("/{bid}/send-to-canvas", status_code=202)
def send_to_canvas(bid: str, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """Send one shared badge to Canvas Credentials, where it appears in the student's Canvas Backpack."""
    from ..integrations import credentials
    from ..services import tasks

    b = db.get(SkillBadge, bid)
    if not b or b.student_id != user.id:
        raise HTTPException(404, "Badge not found")
    if not credentials.enabled():
        raise HTTPException(404, "Canvas Credentials is not configured for this institution")
    if not b.public or b.status != "active":
        raise HTTPException(400, "Share the badge first: only shared badges are sent to Canvas")
    t = tasks.enqueue(db, "credentials.send", {"badge_ids": [b.id]}, b.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


@router.post("/credentials/send", status_code=202)
def send_all_to_canvas(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Send every shared, active badge not yet in Canvas Credentials."""
    from ..integrations import credentials
    from ..services import tasks

    if not credentials.enabled():
        raise HTTPException(404, "Canvas Credentials is not configured")
    t = tasks.enqueue(db, "credentials.send", {}, user.org_id, user.id)
    audit(db, user, "credentials.send_all")
    db.commit()
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


@router.post("/sync")
def sync_all(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    n = badgesvc.sync(db, user.org_id)
    audit(db, user, "badges.sync", issued=n)
    db.commit()
    return {"issued": n}


class RevokeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@router.post("/{bid}/revoke")
def revoke(bid: str, body: RevokeIn, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    b = db.get(SkillBadge, bid)
    if not b or b.org_id != user.org_id:
        raise HTTPException(404, "Badge not found")
    b.status, b.revoked_reason = "revoked", body.reason.strip()
    audit(db, user, "badges.revoke", badge=b.id, reason=b.revoked_reason)
    db.commit()
    if b.credentials_assertion_id:
        from ..services import tasks

        tasks.enqueue(db, "credentials.revoke", {"badge_id": b.id, "reason": b.revoked_reason}, b.org_id, user.id)
    return badgesvc.out(b)


@router.get("/student/{sid}")
def student_badges(sid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Employers, advisors and admins of the same institution see a student's active badges (employers only for students open to matching)."""
    from ..models import StudentProfile

    st = db.get(User, sid)
    if not st or st.org_id != user.org_id or st.role != "student" or user.role not in ("employer", "advisor", "admin", "faculty"):
        raise HTTPException(404, "Student not found")
    prof = db.get(StudentProfile, sid)
    if user.role == "employer" and not (prof and prof.open_to_match):
        raise HTTPException(404, "Student not found")
    return [badgesvc.out(b, public=True) for b in db.scalars(select(SkillBadge).where(SkillBadge.student_id == sid, SkillBadge.status == "active"))]


@public.get("/badges/{token}")
def verify_badge(token: str, db: Session = Depends(get_db)):
    """Public verification of a badge the student chose to share. Reveals nothing for unshared or unknown badges."""
    b = db.scalar(select(SkillBadge).where(SkillBadge.public_token == token))
    if not b or not b.public:
        raise HTTPException(404, "This badge does not exist or is not shared")
    st = db.get(User, b.student_id)
    org = db.get(Organization, b.org_id)
    return badgesvc.out(b, public=True) | {"holder": st.full_name if st else None, "institution": org.name if org else None,
                                           "valid": b.status == "active",
                                           "statement": f"{org.name if org else 'The institution'} confirms this student completed {b.course_code}, "
                                                        f"a course in which faculty confirmed students {b.level} {b.skill.name}."}


# ── Open Badges 3.0 and LinkedIn ───────────────────────────────────────────────
def _ob_parts(db: Session, b: SkillBadge):
    from ..integrations import openbadges as ob

    org, st = db.get(Organization, b.org_id), db.get(User, b.student_id)
    try:
        cred = ob.credential(b, org, st)
        return org, cred, ob.sign(cred)
    except ob.Unavailable as e:
        raise HTTPException(503, str(e))


@router.get("/{bid}/openbadge")
def open_badge(bid: str, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    """The student's badge as a signed Open Badges 3.0 credential, plus a prefilled LinkedIn "Add to profile" link."""
    from ..integrations import openbadges as ob

    b = db.get(SkillBadge, bid)
    if not b or b.student_id != user.id:
        raise HTTPException(404, "Badge not found")
    if b.status != "active":
        raise HTTPException(400, "This badge was revoked")
    org, cred, token = _ob_parts(db, b)
    return {"credential": cred, "jwt": token, "verify_url": f"{ob.base()}/badge/{b.public_token}",
            "linkedin_url": ob.linkedin_url(b, org) if b.public else None,
            "linkedin_note": None if b.public else "Share the badge first: LinkedIn links to its public verification page."}


@router.get("/{bid}/openbadge.jwt")
def open_badge_file(bid: str, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    from fastapi.responses import Response

    b = db.get(SkillBadge, bid)
    if not b or b.student_id != user.id or b.status != "active":
        raise HTTPException(404, "Badge not found")
    _, _, token = _ob_parts(db, b)
    name = f"{b.skill.name}-{b.level}".replace(" ", "_")
    return Response(token, media_type="application/vc+jwt", headers={"Content-Disposition": f'attachment; filename="{name}.jwt"'})


@public.get("/ob/jwks.json")
def ob_jwks():
    from ..integrations import openbadges as ob

    try:
        return ob.jwks()
    except ob.Unavailable as e:
        raise HTTPException(503, str(e))


@public.get("/ob/issuers/{oid}")
def ob_issuer(oid: str, db: Session = Depends(get_db)):
    from ..integrations import openbadges as ob

    org = db.get(Organization, oid)
    if not org:
        raise HTTPException(404, "Issuer not found")
    return {"@context": ob.CONTEXT, **ob.issuer(org)}


@public.get("/ob/achievements/{oid}/{skill_id}/{level}")
def ob_achievement(oid: str, skill_id: int, level: str, db: Session = Depends(get_db)):
    from ..integrations import openbadges as ob
    from ..models import Skill

    org, skill = db.get(Organization, oid), db.get(Skill, skill_id)
    if not org or not skill or level not in ob.LEVEL_VERB:
        raise HTTPException(404, "Achievement not found")
    return {"@context": ob.CONTEXT, **ob.achievement(org, skill, level)}


@public.get("/ob/credentials/{token}")
def ob_credential(token: str, db: Session = Depends(get_db)):
    """A shared badge's signed credential (JSON, with the compact JWT)."""
    b = db.scalar(select(SkillBadge).where(SkillBadge.public_token == token))
    if not b or not b.public:
        raise HTTPException(404, "This credential does not exist or is not shared")
    _, cred, jwt_ = _ob_parts(db, b)
    return {"credential": cred, "jwt": jwt_, "status": b.status}


class VerifyIn(BaseModel):
    credential: str = Field(min_length=20, max_length=50_000)


@public.post("/ob/verify")
def ob_verify(body: VerifyIn, db: Session = Depends(get_db)):
    """Verify an Open Badges 3.0 credential this institution issued: signature, format and current status."""
    from ..integrations import openbadges as ob

    try:
        res = ob.verify(body.credential.strip())
    except ob.Unavailable as e:
        raise HTTPException(503, str(e))
    cred = res.pop("credential", None)
    if cred:
        token = str(cred.get("id", "")).rsplit("/", 1)[-1]
        b = db.scalar(select(SkillBadge).where(SkillBadge.public_token == token))
        active = bool(b and b.status == "active")
        res["checks"].append({"check": "status", "ok": active, "detail": "Not revoked" if active else
                              ("Revoked by the institution" if b else "Unknown credential")})
        res["valid"] = res["valid"] and active
        res["summary"] = {"name": cred.get("name"), "issuer": cred.get("issuer", {}).get("name"), "valid_from": cred.get("validFrom"),
                          "evidence": (cred.get("evidence") or [{}])[0].get("narrative")}
    return res
