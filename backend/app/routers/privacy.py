"""Privacy controls: consent, data export ("download my data") and account deletion.

POLICY_VERSION changes whenever the privacy notice/terms change; users are asked to accept again.
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    CurriculumMapEntry, CurriculumProposal, GapDecision, GapReview, JobSample, PasswordReset, ProposalComment, ProposalReview, SkillBadge,
    SponsoredProject, StackCompletion, StackSubscription, SyllabusVersion, Task,
    Application, AuditLog, Evidence, ForgeDraft, Job, Notification, PlanReview, StudentCourse, StudentProfile, Syllabus, User,
)
from ..security import audit, current_user, require_roles, verify_password

router = APIRouter(prefix="/api/privacy", tags=["privacy"])
POLICY_VERSION = "2026-11"


@router.get("/policy")
def policy():
    return {"version": POLICY_VERSION}


@router.post("/consent")
def consent(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.consent_version, user.consent_at = POLICY_VERSION, datetime.now(timezone.utc)
    audit(db, user, "privacy.consent", version=POLICY_VERSION)
    db.commit()
    return {"version": POLICY_VERSION}


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _row(obj, skip=()) -> dict:
    return {c.name: _iso(getattr(obj, c.name)) for c in obj.__table__.columns if c.name not in skip}


def collect(db: Session, user: User) -> dict:
    """Everything CometIQ stores about a person (password hash and file bytes excluded)."""
    uid = user.id
    data = {"exported_at": datetime.now(timezone.utc).isoformat(), "policy_version": POLICY_VERSION,
            "account": _row(user, skip=("password_hash",)), "organization": user.org.name}
    prof = db.get(StudentProfile, uid)
    if prof:
        data["student_profile"] = _row(prof)
        data["courses"] = [{**_row(sc), "course_code": sc.course.code} for sc in db.scalars(select(StudentCourse).where(StudentCourse.user_id == uid))]
        data["evidence"] = [{**_row(e), "file": {"filename": e.file.filename, "size": e.file.size} if e.file else None}
                            for e in db.scalars(select(Evidence).where(Evidence.student_id == uid))]
        data["plan_reviews"] = [_row(r) for r in db.scalars(select(PlanReview).where(PlanReview.student_id == uid))]
        data["applications"] = [{**_row(a), "job_title": a.job.title, "company": a.job.company}
                                for a in db.scalars(select(Application).where(Application.student_id == uid))]
    data["syllabi"] = [_row(s, skip=("raw_text",)) for s in db.scalars(select(Syllabus).where(Syllabus.owner_id == uid))]
    data["forge_drafts"] = [_row(d) for d in db.scalars(select(ForgeDraft).where(ForgeDraft.owner_id == uid))]
    data["posted_jobs"] = [_row(j) for j in db.scalars(select(Job).where(Job.employer_id == uid))]
    data["notifications"] = [_row(n) for n in db.scalars(select(Notification).where(Notification.user_id == uid))]
    data["activity_log"] = [_row(a) for a in db.scalars(select(AuditLog).where(AuditLog.user_id == uid).order_by(AuditLog.id))]
    return data


@router.get("/export")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    body = json.dumps(collect(db, user), indent=2, default=str)
    audit(db, user, "privacy.export")
    db.commit()
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="cometiq-my-data.json"', "Cache-Control": "no-store"})


def erase(db: Session, user: User) -> None:
    """Delete a person and their personal data. Shared job postings stay (closed); the audit trail is anonymized."""
    uid = user.id
    if user.role == "admin":
        others = db.scalar(select(func.count()).select_from(User).where(User.org_id == user.org_id, User.role == "admin",
                                                                        User.is_active, User.id != uid))
        if not others:
            raise HTTPException(400, "Add another administrator before deleting the last one")
    for model, col in ((Application, Application.student_id), (Evidence, Evidence.student_id), (PlanReview, PlanReview.student_id),
                       (StudentCourse, StudentCourse.user_id), (Notification, Notification.user_id), (ForgeDraft, ForgeDraft.owner_id),
                       (Syllabus, Syllabus.owner_id)):
        for obj in db.scalars(select(model).where(col == uid)):
            db.delete(obj)  # ORM delete so child rows (files, skills, analyses) cascade on every database
    db.flush()
    db.execute(update(Job).where(Job.employer_id == uid).values(employer_id=None, is_open=False))
    db.execute(update(PlanReview).where(PlanReview.advisor_id == uid).values(advisor_id=None))
    db.execute(update(Evidence).where(Evidence.reviewer_id == uid).values(reviewer_id=None))
    db.execute(delete(StudentProfile).where(StudentProfile.user_id == uid))
    db.execute(update(AuditLog).where(AuditLog.user_id == uid).values(user_id=None, detail=None))
    # faculty judgments stay as institutional records of the course, without the reviewer's identity
    db.execute(update(GapReview).where(GapReview.reviewer_id == uid).values(reviewer_id=None))
    db.execute(update(GapDecision).where(GapDecision.reviewer_id == uid).values(reviewer_id=None, reviewer_name=None))
    db.execute(update(SyllabusVersion).where(SyllabusVersion.created_by == uid).values(created_by=None))
    db.execute(delete(SkillBadge).where(SkillBadge.student_id == uid))
    db.execute(delete(StackCompletion).where(StackCompletion.student_id == uid))
    db.execute(delete(StackSubscription).where(StackSubscription.employer_id == uid))
    db.execute(update(SponsoredProject).where(SponsoredProject.employer_id == uid).values(employer_id=None))
    db.execute(update(CurriculumProposal).where(CurriculumProposal.author_id == uid).values(author_id=None, author_name=None))
    db.execute(update(ProposalComment).where(ProposalComment.author_id == uid).values(author_id=None, author_name=None))
    db.execute(update(ProposalReview).where(ProposalReview.reviewer_id == uid).values(reviewer_id=None, reviewer_name=None))
    db.execute(update(CurriculumMapEntry).where(CurriculumMapEntry.set_by_id == uid).values(set_by_id=None, set_by_name=None))
    db.execute(update(JobSample).where(JobSample.created_by == uid).values(created_by=None))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == uid))
    # background jobs they started, and queued/sent emails addressed to them (payloads can hold the address)
    db.execute(delete(Task).where(Task.user_id == uid))
    email = user.email.lower()
    for t in db.scalars(select(Task).where(Task.kind == "email.send")):
        if email in json.dumps(t.payload or {}).lower():
            db.delete(t)
    db.add(AuditLog(org_id=user.org_id, user_id=None, action="privacy.account_deleted", detail={"role": user.role}))
    db.delete(user)


class DeleteIn(BaseModel):
    password: str
    confirm: str


@router.post("/delete-account")
def delete_account(body: DeleteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.confirm.strip().upper() != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm')
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "Password is incorrect")
    erase(db, user)
    db.commit()
    return {"deleted": True}


@router.delete("/admin/users/{uid}")
def admin_delete_user(uid: str, admin: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Administrator erasure (e.g. a FERPA/records request)."""
    u = db.get(User, uid)
    if not u or u.org_id != admin.org_id:
        raise HTTPException(404, "User not found")
    email = u.email
    erase(db, u)
    audit(db, admin, "privacy.admin_erasure", role=u.role)
    db.commit()
    return {"deleted": email}
