"""CometMatch API — student job matching and employer talent matching."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, Concentration, Job, Program, StudentProfile, User
from ..security import audit, require_roles
from ..services import jobs as jobsvc
from ..services import match as matchsvc
from ..services import parser
from ..services import skills as sk
from .jobs import job_out

router = APIRouter(prefix="/api/match", tags=["cometmatch"])
student = require_roles("student")
employer = require_roles("employer")
APP_STATUSES = ("applied", "shortlisted", "interview", "offer", "hired", "rejected")


def _visible_jobs(user: User):
    return select(Job).where(Job.is_open, (Job.org_id == user.org_id) | Job.org_id.is_(None))


# ── Student side ───────────────────────────────────────────────────────────────
@router.get("/me")
def my_profile(user: User = Depends(student), db: Session = Depends(get_db)):
    p = db.get(StudentProfile, user.id) or StudentProfile(user_id=user.id)
    return {"headline": p.headline, "open_to_match": p.open_to_match, "resume_filename": p.resume_filename,
            "resume_preview": (p.resume_text or "")[:1500], "skills": matchsvc.skill_profile(db, user.id)}


class MeIn(BaseModel):
    headline: str | None = Field(None, max_length=300)
    open_to_match: bool = True


@router.put("/me")
def update_me(body: MeIn, user: User = Depends(student), db: Session = Depends(get_db)):
    p = db.get(StudentProfile, user.id)
    if not p:
        p = StudentProfile(user_id=user.id)
        db.add(p)
    p.headline, p.open_to_match = body.headline, body.open_to_match
    db.commit()
    return {"ok": True}


@router.post("/me/resume")
async def upload_resume(file: UploadFile = File(...), user: User = Depends(student), db: Session = Depends(get_db)):
    name, text = await parser.read_upload(file)
    found, engine = sk.extract(text, kind="student resume")
    ids = sk.skill_ids(db, found)
    p = db.get(StudentProfile, user.id)
    if not p:
        p = StudentProfile(user_id=user.id)
        db.add(p)
    p.resume_filename, p.resume_text, p.resume_skills = name, text, sorted(ids.values())
    audit(db, user, "match.resume", skills=len(ids), engine=engine)
    db.commit()
    return {"skills_found": len(ids), "engine": engine, "skills": matchsvc.skill_profile(db, user.id)}


@router.get("/jobs")
def my_matches(role_family: str = "", employment_type: str = "", q: str = "", posted_only: bool = False, limit: int = 40,
               user: User = Depends(student), db: Session = Depends(get_db)):
    skills = matchsvc.student_skills(db, user.id)
    stmt = _visible_jobs(user)
    if role_family:
        stmt = stmt.where(Job.role_family == role_family)
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q}%") | Job.company.ilike(f"%{q}%"))
    if posted_only:
        stmt = stmt.where(Job.employer_id.is_not(None))
    applied = dict(db.execute(select(Application.job_id, Application.status).where(Application.student_id == user.id)).all())
    out = []
    for j in db.scalars(stmt):
        m = matchsvc.score_job(j, skills)
        out.append({**job_out(j), "score": m["score"], "label": m["label"], "summary": m["summary"],
                    "matched": [x["skill"] for x in m["matched"]][:5], "missing": [x["skill"] for x in m["missing"] if x["importance"] == "required"][:4],
                    "can_apply": j.employer_id is not None, "application": applied.get(j.id)})
    out.sort(key=lambda x: (-x["score"], x["title"]))
    return {"has_skills": bool(skills), "items": out[: min(limit, 200)]}


@router.get("/jobs/{jid}")
def match_detail(jid: str, user: User = Depends(student), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or (j.org_id and j.org_id != user.org_id):
        raise HTTPException(404, "Job not found")
    m = matchsvc.score_job(j, matchsvc.student_skills(db, user.id), matchsvc.teaching_courses(db, user.org_id))
    app = db.scalar(select(Application).where(Application.job_id == j.id, Application.student_id == user.id))
    return {"job": job_out(j, True), **m, "can_apply": j.employer_id is not None,
            "application": {"status": app.status, "created_at": app.created_at} if app else None}


class ApplyIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


@router.post("/jobs/{jid}/apply", status_code=201)
def apply(jid: str, body: ApplyIn, user: User = Depends(student), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or not j.is_open or j.org_id != user.org_id or not j.employer_id:
        raise HTTPException(400, "You can apply in CometIQ only to roles posted by partner employers")
    app = db.scalar(select(Application).where(Application.job_id == j.id, Application.student_id == user.id))
    score = matchsvc.score_job(j, matchsvc.student_skills(db, user.id))["score"]
    if app:
        if app.status == "shortlisted" and app.initiated_by == "employer":
            app.status = "applied"  # student accepts an employer invitation
        else:
            raise HTTPException(409, "Already applied")
    else:
        app = Application(job_id=j.id, student_id=user.id, status="applied", initiated_by="student", score=score, note=body.note)
        db.add(app)
    app.score = score
    audit(db, user, "match.apply", job=j.title, score=score)
    db.commit()
    return {"status": app.status, "score": score}


@router.get("/applications")
def my_applications(user: User = Depends(student), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.student_id == user.id).order_by(Application.updated_at.desc()))
    return [{"id": a.id, "status": a.status, "score": a.score, "initiated_by": a.initiated_by, "updated_at": a.updated_at,
             "job": {"id": a.job.id, "title": a.job.title, "company": a.job.company, "location": a.job.location}} for a in rows]


# ── Employer side ──────────────────────────────────────────────────────────────
class ExtractIn(BaseModel):
    title: str
    description: str = ""


@router.post("/employer/extract")
def preview_skills(body: ExtractIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    mapping, engine = jobsvc.extract_job_skills(body.title, body.description)
    return {"engine": engine, "skills": [{"name": k, "importance": v} for k, v in mapping.items()]}


class PostIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    location: str | None = None
    employment_type: str = "Full-time"
    description: str = ""
    url: str | None = None
    skills: list[dict] | None = None  # [{name, importance}] — overrides extraction
    is_open: bool = True


def _own_job(db: Session, user: User, jid: str) -> Job:
    j = db.get(Job, jid)
    if not j or j.org_id != user.org_id or (user.role != "admin" and j.employer_id != user.id):
        raise HTTPException(404, "Job not found")
    return j


@router.get("/employer/jobs")
def employer_jobs(user: User = Depends(employer), db: Session = Depends(get_db)):
    q = select(Job).where(Job.org_id == user.org_id, Job.employer_id.is_not(None))
    if user.role != "admin":
        q = q.where(Job.employer_id == user.id)
    counts = dict(db.execute(select(Application.job_id, func.count()).group_by(Application.job_id)).all())
    return [{**job_out(j), "applications": counts.get(j.id, 0)} for j in db.scalars(q.order_by(Job.posted_at.desc()))]


@router.post("/employer/jobs", status_code=201)
def post_job(body: PostIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    override = {s["name"]: s.get("importance", "required") for s in body.skills} if body.skills else None
    j = jobsvc.upsert_job(db, {"title": body.title, "company": user.company or user.org.name, "location": body.location,
                               "employment_type": body.employment_type, "description": body.description, "url": body.url,
                               "source": "employer"}, org_id=user.org_id, employer_id=user.id, skills_override=override)
    audit(db, user, "match.job.post", title=body.title)
    db.commit()
    return job_out(j, True)


@router.put("/employer/jobs/{jid}")
def update_job(jid: str, body: PostIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    j = _own_job(db, user, jid)
    j.title, j.location, j.employment_type, j.description, j.url, j.is_open = (
        body.title, body.location, body.employment_type, body.description, body.url, body.is_open)
    if body.skills is not None:
        jobsvc.set_job_skills(db, j, {s["name"]: s.get("importance", "required") for s in body.skills})
    db.commit()
    return job_out(j, True)


@router.get("/employer/jobs/{jid}/candidates")
def candidates(jid: str, min_score: float = 0, user: User = Depends(employer), db: Session = Depends(get_db)):
    j = _own_job(db, user, jid)
    apps = {a.student_id: a for a in db.scalars(select(Application).where(Application.job_id == j.id))}
    rows = db.execute(select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id)
                      .where(User.org_id == user.org_id, User.role == "student", User.is_active)).all()
    progs = {p.id: p.name for p in db.scalars(select(Program).where(Program.org_id == user.org_id))}
    concs = {c.id: c.name for c in db.scalars(select(Concentration))}
    out = []
    for u, prof in rows:
        if not prof.open_to_match and u.id not in apps:
            continue
        m = matchsvc.score_job(j, matchsvc.student_skills(db, u.id))
        if m["score"] < min_score and u.id not in apps:
            continue
        a = apps.get(u.id)
        out.append({"student": {"id": u.id, "name": u.full_name, "headline": prof.headline, "program": progs.get(prof.program_id),
                                "concentration": concs.get(prof.concentration_id), "career_goal": prof.career_goal,
                                "has_resume": bool(prof.resume_filename)},
                    **m, "application": {"status": a.status, "initiated_by": a.initiated_by} if a else None})
    out.sort(key=lambda x: (x["application"] is None, -x["score"]))
    return {"job": job_out(j), "candidates": out}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(applied|shortlisted|interview|offer|hired|rejected)$")


@router.post("/employer/jobs/{jid}/candidates/{sid}")
def set_status(jid: str, sid: str, body: StatusIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    j = _own_job(db, user, jid)
    stu = db.get(User, sid)
    if not stu or stu.org_id != user.org_id or stu.role != "student":
        raise HTTPException(404, "Student not found")
    a = db.scalar(select(Application).where(Application.job_id == j.id, Application.student_id == sid))
    score = matchsvc.score_job(j, matchsvc.student_skills(db, sid))["score"]
    if not a:
        a = Application(job_id=j.id, student_id=sid, status=body.status, initiated_by="employer", score=score)
        db.add(a)
    a.status, a.score = body.status, score
    audit(db, user, "match.candidate.status", job=j.title, student=stu.email, status=body.status)
    db.commit()
    return {"status": a.status}


@router.get("/employer/pipeline")
def pipeline(user: User = Depends(employer), db: Session = Depends(get_db)):
    q = select(Application).join(Job).where(Job.org_id == user.org_id)
    if user.role != "admin":
        q = q.where(Job.employer_id == user.id)
    out = {s: [] for s in APP_STATUSES}
    for a in db.scalars(q.order_by(Application.score.desc())):
        out[a.status].append({"id": a.id, "score": a.score, "student": {"id": a.student.id, "name": a.student.full_name},
                              "job": {"id": a.job.id, "title": a.job.title}, "initiated_by": a.initiated_by})
    return out
