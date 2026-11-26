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
from ..services.notify import notify
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
    skills, bonuses = matchsvc.student_profile(db, user.id)
    ql = q.lower()
    applied = dict(db.execute(select(Application.job_id, Application.status).where(Application.student_id == user.id)).all())
    out = []
    for j in matchsvc.open_jobs(db, user.org_id):   # cached, read-only
        if (role_family and j.role_family != role_family) or (employment_type and j.employment_type != employment_type) \
                or (posted_only and j.employer_id is None) or (ql and ql not in j.title.lower() and ql not in (j.company or "").lower()):
            continue
        m = matchsvc.score_job(j, skills, bonuses=bonuses)
        out.append({**j.out, "score": m["score"], "bonus": m["bonus"], "label": m["label"], "summary": m["summary"],
                    "matched": [x["skill"] for x in m["matched"]][:5], "missing": [x["skill"] for x in m["missing"] if x["importance"] == "required"][:4],
                    "can_apply": j.employer_id is not None, "application": applied.get(j.id)})
    out.sort(key=lambda x: (-x["score"], x["title"]))
    return {"has_skills": bool(skills), "items": out[: min(limit, 200)]}


@router.get("/jobs/{jid}")
def match_detail(jid: str, user: User = Depends(student), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or (j.org_id and j.org_id != user.org_id):
        raise HTTPException(404, "Job not found")
    sk_, bn = matchsvc.student_profile(db, user.id)
    m = matchsvc.score_job(j, sk_, matchsvc.teaching_courses(db, user.org_id), bonuses=bn)
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
    sk_, bn = matchsvc.student_profile(db, user.id)
    score = matchsvc.score_job(j, sk_, bonuses=bn)["score"]
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
    employer_user = db.get(User, j.employer_id)
    if employer_user:
        notify(db, employer_user, "match.applied", f"New applicant: {user.full_name}",
               f"{user.full_name} applied to {j.title} with a {round(score)}% skill fit.", "/match")
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
def candidates(jid: str, min_score: float = 0, limit: int = 100, user: User = Depends(employer), db: Session = Depends(get_db)):
    from ..services.cache import cached

    j = _own_job(db, user, jid)
    return cached(db, user.org_id, ("candidates", jid, min_score, limit), lambda: _candidates(j, min_score, limit, user, db))


def _candidates(j, min_score: float, limit: int, user: User, db: Session):
    apps = {a.student_id: a for a in db.scalars(select(Application).where(Application.job_id == j.id))}
    rows = db.execute(select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id)
                      .where(User.org_id == user.org_id, User.role == "student", User.is_active)).all()
    progs = {p.id: p.name for p in db.scalars(select(Program).where(Program.org_id == user.org_id))}
    concs = {c.id: c.name for c in db.scalars(select(Concentration))}
    out = []
    rows = [(u, prof) for u, prof in rows if prof.open_to_match or u.id in apps]
    all_sk = matchsvc.students_skills(db, [u.id for u, _ in rows])
    all_bn = matchsvc.students_bonuses(db, [u.id for u, _ in rows])
    for u, prof in rows:
        sk_, bn = all_sk.get(u.id, {}), all_bn.get(u.id, [])
        m = matchsvc.score_job(j, sk_, bonuses=bn)
        if m["score"] < min_score and u.id not in apps:
            continue
        a = apps.get(u.id)
        out.append({"student": {"id": u.id, "name": u.full_name, "headline": prof.headline, "program": progs.get(prof.program_id),
                                "concentration": concs.get(prof.concentration_id), "career_goal": prof.career_goal,
                                "has_resume": bool(prof.resume_filename)},
                    **m, "application": {"status": a.status, "initiated_by": a.initiated_by} if a else None})
    out.sort(key=lambda x: (x["application"] is None, -x["score"]))
    limit = max(1, min(limit, 500))
    return {"job": job_out(j), "candidates": out[:limit], "total": len(out), "limit": limit}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(applied|shortlisted|interview|offer|hired|rejected)$")


@router.post("/employer/jobs/{jid}/candidates/{sid}")
def set_status(jid: str, sid: str, body: StatusIn, user: User = Depends(employer), db: Session = Depends(get_db)):
    j = _own_job(db, user, jid)
    stu = db.get(User, sid)
    if not stu or stu.org_id != user.org_id or stu.role != "student":
        raise HTTPException(404, "Student not found")
    a = db.scalar(select(Application).where(Application.job_id == j.id, Application.student_id == sid))
    sk_, bn = matchsvc.student_profile(db, sid)
    score = matchsvc.score_job(j, sk_, bonuses=bn)["score"]
    if not a:
        a = Application(job_id=j.id, student_id=sid, status=body.status, initiated_by="employer", score=score)
        db.add(a)
    a.status, a.score = body.status, score
    audit(db, user, "match.candidate.status", job=j.title, student=stu.email, status=body.status)
    msg = {"shortlisted": (f"{j.company} invited you to apply", f"{j.company} shortlisted you for {j.title}. Open CometMatch to accept the invitation."),
           "interview": (f"Interview stage: {j.title}", f"{j.company} moved your application for {j.title} to the interview stage."),
           "offer": (f"Offer: {j.title}", f"Congratulations — {j.company} marked an offer for {j.title}."),
           "hired": (f"Hired: {j.title}", f"{j.company} marked you as hired for {j.title}."),
           "rejected": (f"Update on {j.title}", f"{j.company} decided not to move forward with your application for {j.title}.")}.get(body.status)
    if msg:
        notify(db, stu, f"match.{body.status}", msg[0], msg[1], "/match")
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


# ── AI explanations, resume tips, learn-next ───────────────────────────────────
from ..services import match_ai  # noqa: E402


@router.post("/jobs/{jid}/explain")
def explain_for_student(jid: str, user: User = Depends(student), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or (j.org_id and j.org_id != user.org_id):
        raise HTTPException(404, "Job not found")
    sk_, bn = matchsvc.student_profile(db, user.id)
    m = matchsvc.score_job(j, sk_, matchsvc.teaching_courses(db, user.org_id), bonuses=bn)
    exp, engine = match_ai.explain(j, m, "student", user.full_name)
    return {**exp.model_dump(), "engine": engine}


@router.post("/me/resume-tips")
def resume_tips(user: User = Depends(student), db: Session = Depends(get_db)):
    review, engine = match_ai.resume_review(db, user.id, user.org_id)
    return {**review.model_dump(), "engine": engine}


@router.get("/learn-next")
def learn_next(limit: int = 8, user: User = Depends(student), db: Session = Depends(get_db)):
    prof = db.get(StudentProfile, user.id)
    stmt = _visible_jobs(user)
    if prof and prof.career_goal:
        goal_jobs = list(db.scalars(stmt.where(Job.role_family == prof.career_goal)))
        jobs = goal_jobs if len(goal_jobs) >= 3 else list(db.scalars(stmt))
    else:
        jobs = list(db.scalars(stmt))
    return {"career_goal": prof.career_goal if prof else None, "skills": match_ai.learn_next(db, user.id, user.org_id, jobs, min(limit, 15))}


@router.post("/employer/jobs/{jid}/candidates/{sid}/explain")
def explain_for_employer(jid: str, sid: str, user: User = Depends(employer), db: Session = Depends(get_db)):
    j = _own_job(db, user, jid)
    stu = db.get(User, sid)
    prof = db.get(StudentProfile, sid)
    if not stu or stu.org_id != user.org_id or stu.role != "student" or not prof:
        raise HTTPException(404, "Student not found")
    if not prof.open_to_match and not db.scalar(select(Application.id).where(Application.job_id == j.id, Application.student_id == sid)):
        raise HTTPException(404, "Student not found")
    sk_, bn = matchsvc.student_profile(db, sid)
    m = matchsvc.score_job(j, sk_, matchsvc.teaching_courses(db, user.org_id), bonuses=bn)
    exp, engine = match_ai.explain(j, m, "employer", stu.full_name)
    return {**exp.model_dump(), "engine": engine}


# ── Employer talent search (all students who opted in) ─────────────────────────
@router.get("/employer/talent")
def talent_search(skills: str = "", q: str = "", program_id: str = "", goal: str = "", verified_only: bool = False,
                  faculty_verified: bool = False,
                  limit: int = 50, user: User = Depends(employer), db: Session = Depends(get_db)):
    from ..models import Evidence, Skill

    want = [int(x) for x in skills.split(",") if x.strip().isdigit()][:15]
    names = {s.id: s.name for s in db.scalars(select(Skill).where(Skill.id.in_(want)))} if want else {}
    stmt = (select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id)
            .where(User.org_id == user.org_id, User.role == "student", User.is_active, StudentProfile.open_to_match))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | StudentProfile.headline.ilike(f"%{q}%"))
    if program_id:
        stmt = stmt.where(StudentProfile.program_id == program_id)
    if goal:
        stmt = stmt.where(StudentProfile.career_goal == goal)
    progs = {p.id: p.name for p in db.scalars(select(Program).where(Program.org_id == user.org_id))}
    verified: dict[str, list[str]] = {}
    for e in db.scalars(select(Evidence).where(Evidence.org_id == user.org_id, Evidence.status == "verified")):
        verified.setdefault(e.student_id, []).append(e.title)
    out = []
    pairs = [(u, prof) for u, prof in db.execute(stmt).all() if not verified_only or u.id in verified]
    all_sk = matchsvc.students_skills(db, [u.id for u, _ in pairs])
    skill_names = {sk.id: sk.name for sk in db.scalars(select(Skill))}
    for u, prof in pairs:
        sk_ = all_sk.get(u.id, {})
        if want:
            hits = [{"skill": names[s], "faculty_verified": sk_.get(s, {}).get("faculty_verified", False),
                     "level": round(min(sk_.get(s, {}).get("level", 0), 1), 2) if not faculty_verified or sk_.get(s, {}).get("faculty_verified") else 0.0,
                     "sources": list(dict.fromkeys(sk_.get(s, {}).get("sources", [])))[:3]} for s in want if s in names]
            score = round(100 * sum(h["level"] for h in hits) / max(len(hits), 1), 1)
            if score == 0:
                continue
        else:
            hits, score = [], float(len(sk_))
        top = sorted(((v["level"], s) for s, v in sk_.items()), reverse=True)[:8]
        top_names = {s: skill_names[s] for _, s in top if s in skill_names}
        fv = [s for s, v in sk_.items() if v.get("faculty_verified")]
        if faculty_verified and not want and not fv:
            continue
        top_names_all = {s: skill_names[s] for s in fv if s in skill_names}
        out.append({"student": {"id": u.id, "name": u.full_name, "headline": prof.headline, "program": progs.get(prof.program_id),
                                "career_goal": prof.career_goal},
                    "score": score, "skills": hits, "top_skills": [top_names[s] for _, s in top if s in top_names],
                    "verified": verified.get(u.id, []), "skill_count": len(sk_),
                    "faculty_verified": sorted(top_names_all[s] for s, v in sk_.items() if v.get("faculty_verified") and s in top_names_all)[:10]})
    out.sort(key=lambda x: -x["score"])
    return {"searched": [names[s] for s in want if s in names], "results": out[: min(limit, 200)]}
