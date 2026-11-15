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
    return {"badges": rows, "pending": pending}


class ShareIn(BaseModel):
    public: bool


@router.put("/{bid}/share")
def share(bid: str, body: ShareIn, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    b = db.get(SkillBadge, bid)
    if not b or b.student_id != user.id:
        raise HTTPException(404, "Badge not found")
    b.public = body.public
    db.commit()
    return badgesvc.out(b)


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
