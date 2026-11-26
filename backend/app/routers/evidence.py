"""Skill evidence portal: students document courses, certifications and projects (with proof);
admins and advisors verify them. Verified evidence feeds CometMatch scores and CometPath progress."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Course, CourseSkill, Evidence, EvidenceFile, Skill, StudentCourse, User
from ..security import audit, current_user, require_roles
from ..services import skills as sk
from ..services.notify import notify

router = APIRouter(prefix="/api/evidence", tags=["evidence"])
student = require_roles("student")
reviewer = require_roles("advisor")  # admins are always allowed
KINDS = ("course", "certification", "project", "experience")
DEFAULT_BONUS = {"certification": 10, "project": 5, "experience": 5, "course": 0}
MAX_BONUS = 20
FILE_TYPES = {  # magic bytes → content type
    b"%PDF": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp",
}


def _sniff(data: bytes) -> str | None:
    return next((ct for magic, ct in FILE_TYPES.items() if data.startswith(magic)), None)


def _out(db: Session, e: Evidence, with_student: bool = False) -> dict:
    names = {s.id: s.name for s in db.scalars(select(Skill).where(Skill.id.in_(e.skills or [])))} if e.skills else {}
    d = {"id": e.id, "kind": e.kind, "title": e.title, "issuer": e.issuer, "description": e.description,
         "course": {"id": e.course.id, "code": e.course.code, "title": e.course.title} if e.course else None,
         "skills": [{"id": i, "name": names[i]} for i in e.skills or [] if i in names],
         "credential_id": e.credential_id, "credential_url": e.credential_url, "issued_on": e.issued_on,
         "status": e.status, "bonus_points": e.bonus_points, "review_note": e.review_note, "reviewed_at": e.reviewed_at,
         "created_at": e.created_at, "suggested_bonus": DEFAULT_BONUS.get(e.kind, 0),
         "file": {"filename": e.file.filename, "content_type": e.file.content_type, "size": e.file.size} if e.file else None}
    if with_student:
        d["student"] = {"id": e.student.id, "name": e.student.full_name, "email": e.student.email}
    return d


def _detect_skills(db: Session, text: str, course: Course | None) -> list[int]:
    found, _ = sk.extract(text, kind="student-described learning / certification")
    ids = set(sk.skill_ids(db, found).values())
    if course:
        ids |= {cs.skill_id for cs in db.scalars(select(CourseSkill).where(CourseSkill.course_id == course.id, CourseSkill.weight >= 1))}
    return sorted(ids)


# ── Student ────────────────────────────────────────────────────────────────────
@router.get("/mine")
def mine(user: User = Depends(student), db: Session = Depends(get_db)):
    rows = db.scalars(select(Evidence).where(Evidence.student_id == user.id).order_by(Evidence.created_at.desc()))
    return [_out(db, e) for e in rows]


@router.post("", status_code=201)
async def submit(
    kind: str = Form(...), title: str = Form(...), description: str = Form(""), issuer: str = Form(""),
    course_id: str = Form(""), credential_id: str = Form(""), credential_url: str = Form(""), issued_on: str = Form(""),
    file: UploadFile | None = File(None), user: User = Depends(student), db: Session = Depends(get_db),
):
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(KINDS)}")
    if len(title.strip()) < 3:
        raise HTTPException(400, "Give the course or certification a title")
    if kind == "certification" and not (file and file.filename) and not credential_url.strip():
        raise HTTPException(400, "Certifications need proof: upload the certificate or add a verification link")
    course = db.get(Course, course_id) if course_id else None
    if course and course.org_id != user.org_id:
        course = None
    e = Evidence(org_id=user.org_id, student_id=user.id, kind=kind, title=title.strip()[:300], issuer=issuer.strip() or None,
                 course_id=course.id if course else None, description=description.strip()[:5000],
                 credential_id=credential_id.strip() or None, credential_url=credential_url.strip() or None, issued_on=issued_on.strip() or None)
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > get_settings().MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, "File too large")
        ct = _sniff(data)
        if not ct:
            raise HTTPException(400, "Upload a PDF, PNG, JPG or WebP file")
        e.file = EvidenceFile(filename=file.filename[:300], content_type=ct, size=len(data), data=data)
    e.skills = _detect_skills(db, f"{title}\n{issuer}\n{description}", course)
    db.add(e)
    audit(db, user, "evidence.submit", kind=kind, title=e.title)
    db.commit()
    return _out(db, e)


def _get(db: Session, user: User, eid: str) -> Evidence:
    e = db.get(Evidence, eid)
    if not e or e.org_id != user.org_id:
        raise HTTPException(404, "Not found")
    if user.role == "student" and e.student_id != user.id:
        raise HTTPException(404, "Not found")
    if user.role not in ("student", "admin", "advisor"):
        raise HTTPException(403, "Not allowed")
    return e


class SkillsIn(BaseModel):
    skill_ids: list[int]


@router.put("/{eid}/skills")
def set_skills(eid: str, body: SkillsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get(db, user, eid)
    if user.role == "student" and e.status == "verified":
        raise HTTPException(409, "Verified evidence is locked")
    valid = set(db.scalars(select(Skill.id).where(Skill.id.in_(body.skill_ids))))
    e.skills = sorted(valid)
    db.commit()
    return _out(db, e)


@router.delete("/{eid}")
def delete(eid: str, user: User = Depends(student), db: Session = Depends(get_db)):
    e = _get(db, user, eid)
    if e.status == "verified" and user.role == "student":
        raise HTTPException(409, "Verified evidence can only be removed by an administrator")
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.get("/{eid}/file")
def get_file(eid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _get(db, user, eid)
    if not e.file:
        raise HTTPException(404, "No file attached")
    return Response(e.file.data, media_type=e.file.content_type,
                    headers={"Content-Disposition": f'inline; filename="{e.file.filename}"', "X-Content-Type-Options": "nosniff",
                             "Cache-Control": "private, no-store"})


# ── Reviewer (admin / advisor) ─────────────────────────────────────────────────
@router.get("/queue")
def queue(status: str = "pending", user: User = Depends(reviewer), db: Session = Depends(get_db)):
    q = select(Evidence).where(Evidence.org_id == user.org_id)
    if status != "all":
        q = q.where(Evidence.status == status)
    rows = db.scalars(q.order_by(Evidence.created_at.asc() if status == "pending" else Evidence.created_at.desc()).limit(200))
    return [_out(db, e, True) for e in rows]


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(verified|rejected)$")
    bonus_points: int | None = Field(None, ge=0, le=MAX_BONUS)
    note: str | None = Field(None, max_length=2000)
    skill_ids: list[int] | None = None


@router.post("/{eid}/review")
def review(eid: str, body: ReviewIn, user: User = Depends(reviewer), db: Session = Depends(get_db)):
    e = _get(db, user, eid)
    if body.decision == "rejected" and not (body.note or "").strip():
        raise HTTPException(400, "Tell the student why it was rejected")
    if body.skill_ids is not None:
        e.skills = sorted(set(db.scalars(select(Skill.id).where(Skill.id.in_(body.skill_ids)))))
    e.status = body.decision
    e.bonus_points = (body.bonus_points if body.bonus_points is not None else DEFAULT_BONUS.get(e.kind, 0)) if body.decision == "verified" else 0
    e.review_note, e.reviewer_id, e.reviewed_at = body.note, user.id, datetime.now(timezone.utc)
    # A verified catalog course counts as completed in CometPath
    if body.decision == "verified" and e.kind == "course" and e.course_id:
        sc = db.scalar(select(StudentCourse).where(StudentCourse.user_id == e.student_id, StudentCourse.course_id == e.course_id))
        if sc:
            sc.status = "completed"
        else:
            db.add(StudentCourse(user_id=e.student_id, course_id=e.course_id, status="completed", term=e.issued_on))
    db.flush()
    badges_issued = 0
    if body.decision == "verified" and e.kind == "course":
        from ..services import badges as badgesvc

        badges_issued = badgesvc.sync(db, e.org_id, e.student_id)
    audit(db, user, f"evidence.{body.decision}", title=e.title, student=e.student.email, bonus=e.bonus_points)
    if body.decision == "verified":
        notify(db, e.student, "evidence.verified", f"Verified: {e.title}",
               f"{user.full_name} verified your {e.kind}. Its skills now count fully in CometMatch"
               + (f", and it adds +{e.bonus_points} bonus points to jobs that need them." if e.bonus_points else ".")
               + (f" You earned {badges_issued} faculty-verified skill badge{'s' if badges_issued != 1 else ''}." if badges_issued else ""), "/match")
    else:
        notify(db, e.student, "evidence.rejected", f"Not verified: {e.title}",
               f"{user.full_name} could not verify this item: {body.note}", "/match")
    db.commit()
    return _out(db, e, True)
