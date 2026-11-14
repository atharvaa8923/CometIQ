"""CometPath API — student profile, degree progress, recommendations and plans."""
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..db import get_db
from ..models import Concentration, Course, Evidence, PlanReview, Program, StudentCourse, StudentProfile, User
from ..security import audit, require_roles
from ..services import path as pathsvc
from ..services import reports
from ..services.notify import notify, notify_role

router = APIRouter(prefix="/api/path", tags=["cometpath"])
student = require_roles("student")


def _profile(db: Session, user: User) -> StudentProfile:
    p = db.get(StudentProfile, user.id)
    if not p:
        p = StudentProfile(user_id=user.id)
        db.add(p)
        db.flush()
    return p


def _profile_out(p: StudentProfile) -> dict:
    return {"program_id": p.program_id, "concentration_id": p.concentration_id, "career_goal": p.career_goal,
            "start_term": p.start_term, "credits_per_term": p.credits_per_term, "include_summer": p.include_summer}


@router.get("/profile")
def get_profile(user: User = Depends(student), db: Session = Depends(get_db)):
    p = _profile(db, user)
    db.commit()
    return {**_profile_out(p), "career_goals": list(ROLE_FAMILIES)}


class ProfileIn(BaseModel):
    program_id: str | None = None
    concentration_id: str | None = None
    career_goal: str | None = None
    start_term: str = Field("Fall 2026", pattern=r"^(Spring|Summer|Fall) \d{4}$")
    credits_per_term: int = Field(9, ge=3, le=18)
    include_summer: bool = False


@router.put("/profile")
def put_profile(body: ProfileIn, user: User = Depends(student), db: Session = Depends(get_db)):
    p = _profile(db, user)
    if body.program_id:
        prog = db.get(Program, body.program_id)
        if not prog or prog.org_id != user.org_id:
            raise HTTPException(404, "Program not found")
    if body.concentration_id:
        c = db.get(Concentration, body.concentration_id)
        if not c or c.program_id != body.program_id:
            raise HTTPException(400, "Concentration does not belong to the program")
    if body.career_goal and body.career_goal not in ROLE_FAMILIES:
        raise HTTPException(400, "Unknown career goal")
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, user, "path.profile", career_goal=body.career_goal)
    db.commit()
    return _profile_out(p)


def _courses(rows: dict[str, StudentCourse]) -> list[dict]:
    return sorted(({"id": sc.id, "course_id": sc.course_id, "code": sc.course.code, "title": sc.course.title, "credits": sc.course.credits,
                    "status": sc.status, "term": sc.term, "grade": sc.grade} for sc in rows.values()), key=lambda x: (x["status"], x["code"]))


@router.get("/overview")
def overview(user: User = Depends(student), db: Session = Depends(get_db)):
    prof, rows = pathsvc.student_state(db, user.id)
    prof = prof or _profile(db, user)
    g = pathsvc.load_graph(db, user.org_id)
    vec, n = pathsvc.career_vector(db, prof.career_goal, user.org_id)
    done = {cid for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    planned = set(rows)
    return {"profile": _profile_out(prof), "progress": pathsvc.progress(db, prof, rows, g), "courses": _courses(rows),
            "readiness": pathsvc.career_readiness(g, planned, done, vec, n, prof.career_goal)}


@router.get("/recommendations")
def recs(user: User = Depends(student), db: Session = Depends(get_db)):
    prof, rows = pathsvc.student_state(db, user.id)
    if not prof:
        return {"eligible": [], "blocked": []}
    return pathsvc.recommendations(db, prof, rows, pathsvc.load_graph(db, user.org_id), user.org_id)


class CourseIn(BaseModel):
    course_id: str
    status: str = Field(pattern="^(completed|enrolled|planned)$")
    term: str | None = None
    grade: str | None = Field(None, max_length=4)


@router.post("/courses", status_code=201)
def add_course(body: CourseIn, user: User = Depends(student), db: Session = Depends(get_db)):
    c = db.get(Course, body.course_id)
    if not c or c.org_id != user.org_id:
        raise HTTPException(404, "Course not found")
    _, rows = pathsvc.student_state(db, user.id)
    g = pathsvc.load_graph(db, user.org_id)
    warning = None
    if body.status != "completed":
        have = {cid for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
        missing = pathsvc.unmet_groups(g, c.id, have)
        if missing:
            warning = "Missing prerequisites: " + "; ".join(" or ".join(g.courses[o].code for o in grp if o in g.courses) for grp in missing)
    sc = rows.get(c.id)
    if sc:
        sc.status, sc.term, sc.grade = body.status, body.term, body.grade
    else:
        db.add(StudentCourse(user_id=user.id, course_id=c.id, status=body.status, term=body.term, grade=body.grade))
    db.commit()
    return {"ok": True, "warning": warning}


@router.delete("/courses/{course_id}")
def remove_course(course_id: str, user: User = Depends(student), db: Session = Depends(get_db)):
    db.execute(delete(StudentCourse).where(StudentCourse.user_id == user.id, StudentCourse.course_id == course_id))
    db.commit()
    return {"ok": True}


@router.post("/plan")
def plan(save: bool = False, user: User = Depends(student), db: Session = Depends(get_db)):
    prof, rows = pathsvc.student_state(db, user.id)
    if not prof or not prof.program_id:
        raise HTTPException(400, "Choose your program first")
    # regenerate from completed/enrolled only (previous plan is replaced)
    base = {cid: sc for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    result = pathsvc.generate_plan(db, prof, base, pathsvc.load_graph(db, user.org_id), user.org_id)
    if save:
        db.execute(delete(StudentCourse).where(StudentCourse.user_id == user.id, StudentCourse.status == "planned"))
        for t in result["terms"]:
            for c in t["courses"]:
                db.add(StudentCourse(user_id=user.id, course_id=c["id"], status="planned", term=t["term"]))
        audit(db, user, "path.plan.save", terms=len(result["terms"]))
        db.commit()
    return result


# ── What-if plans ──────────────────────────────────────────────────────────────


class WhatIfIn(BaseModel):
    program_id: str
    concentration_id: str | None = None
    career_goal: str | None = None


def _summary(p: dict) -> dict:
    return {k: p.get(k) for k in ("program", "concentration", "career_goal", "graduation_term", "planned_sch", "total_sch",
                                   "required_sch", "counted_courses", "not_counted_courses")} | {
        "terms_left": len(p.get("terms", [])), "readiness_now": p["readiness"]["now"] if p.get("readiness") else 0,
        "readiness_with_plan": p["readiness"]["with_plan"] if p.get("readiness") else 0}


@router.post("/what-if")
def what_if(body: WhatIfIn, user: User = Depends(student), db: Session = Depends(get_db)):
    prof, rows = pathsvc.student_state(db, user.id)
    if not prof:
        raise HTTPException(400, "Set up your profile first")
    prog = db.get(Program, body.program_id)
    if not prog or prog.org_id != user.org_id:
        raise HTTPException(404, "Program not found")
    if body.concentration_id and not any(c.id == body.concentration_id for c in prog.concentrations):
        raise HTTPException(400, "Concentration does not belong to the program")
    if body.career_goal and body.career_goal not in ROLE_FAMILIES:
        raise HTTPException(400, "Unknown career goal")
    base = {cid: sc for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    g = pathsvc.load_graph(db, user.org_id)
    current = pathsvc.generate_plan(db, prof, base, g, user.org_id) if prof.program_id else None
    hypo = SimpleNamespace(program_id=prog.id, concentration_id=body.concentration_id, career_goal=body.career_goal or prof.career_goal,
                           start_term=prof.start_term, credits_per_term=prof.credits_per_term, include_summer=prof.include_summer)
    alt = pathsvc.generate_plan(db, hypo, base, g, user.org_id)
    out = {"current": _summary(current) if current else None, "what_if": _summary(alt), "plan": alt}
    if current:
        ck = lambda t: pathsvc.term_key(t) if t else (0, 0)  # noqa: E731
        diff = (ck(alt["graduation_term"])[0] * 3 + ck(alt["graduation_term"])[1]) - (ck(current["graduation_term"])[0] * 3 + ck(current["graduation_term"])[1])
        out["comparison"] = {"extra_sch": alt["planned_sch"] - current["planned_sch"], "term_shift": diff,
                             "readiness_change": round(alt["readiness"]["with_plan"] - current["readiness"]["with_plan"], 1)}
    return out


# ── Advisor review (student side) ──────────────────────────────────────────────
def _review_out(r: PlanReview | None, db: Session) -> dict | None:
    if not r:
        return None
    current = {c["id"] for t in pathsvc.saved_plan(db, r.student_id) for c in t["courses"]}
    submitted = {c["id"] for t in r.snapshot.get("terms", []) for c in t["courses"]}
    return {"id": r.id, "status": r.status, "student_note": r.student_note, "advisor_note": r.advisor_note,
            "advisor": r.advisor.full_name if r.advisor else None, "created_at": r.created_at, "reviewed_at": r.reviewed_at,
            "changed_since": current != submitted}


def _latest_review(db: Session, student_id: str) -> PlanReview | None:
    return db.scalar(select(PlanReview).where(PlanReview.student_id == student_id).order_by(PlanReview.created_at.desc()))


class SubmitIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


@router.get("/review")
def my_review(user: User = Depends(student), db: Session = Depends(get_db)):
    return _review_out(_latest_review(db, user.id), db)


@router.post("/review", status_code=201)
def submit_review(body: SubmitIn, user: User = Depends(student), db: Session = Depends(get_db)):
    prof, rows = pathsvc.student_state(db, user.id)
    terms = pathsvc.saved_plan(db, user.id)
    if not prof or not prof.program_id or not terms:
        raise HTTPException(400, "Save a semester plan before submitting it for review")
    g = pathsvc.load_graph(db, user.org_id)
    vec, n = pathsvc.career_vector(db, prof.career_goal, user.org_id)
    done = {cid for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    prog = db.get(Program, prof.program_id)
    snapshot = {"program": prog.name, "concentration": next((c.name for c in prog.concentrations if c.id == prof.concentration_id), None),
                "career_goal": prof.career_goal, "terms": terms,
                "readiness": pathsvc.career_readiness(g, set(rows), done, vec, n, prof.career_goal)}
    pending = db.scalar(select(PlanReview).where(PlanReview.student_id == user.id, PlanReview.status == "submitted"))
    r = pending or PlanReview(org_id=user.org_id, student_id=user.id)
    r.snapshot, r.student_note, r.status, r.created_at = snapshot, body.note, "submitted", datetime.now(timezone.utc)
    if not pending:
        db.add(r)
    audit(db, user, "path.review.submit")
    notify_role(db, user.org_id, "advisor", "path.review.submitted", f"Plan to review: {user.full_name}",
                f"{user.full_name} submitted a degree plan ({snapshot['program']}) for review."
                + (f" Note: {body.note}" if body.note else ""), "/advising")
    db.commit()
    return _review_out(r, db)


# ── PDF export ─────────────────────────────────────────────────────────────────
def plan_report(db: Session, stu: User) -> bytes:
    prof, rows = pathsvc.student_state(db, stu.id)
    prof = prof or StudentProfile(user_id=stu.id)
    g = pathsvc.load_graph(db, stu.org_id)
    vec, n = pathsvc.career_vector(db, prof.career_goal, stu.org_id)
    done = {cid for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    prog = db.get(Program, prof.program_id) if prof.program_id else None
    rv = _review_out(_latest_review(db, stu.id), db)
    if rv and rv.get("reviewed_at"):
        rv["reviewed_at"] = rv["reviewed_at"].strftime("%b %d, %Y")
    return reports.plan_pdf({
        "student": stu.full_name, "program": prog.name if prog else None,
        "concentration": next((c.name for c in prog.concentrations if c.id == prof.concentration_id), None) if prog else None,
        "career_goal": prof.career_goal, "generated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
        "progress": pathsvc.progress(db, prof, rows, g) if prog else {"sch": {"completed": 0, "enrolled": 0, "planned": 0}, "total_sch": 0, "core": {"done": 0, "total": 0}},
        "completed": [c for c in _courses(rows) if c["status"] in pathsvc.TAKEN],
        "terms": pathsvc.saved_plan(db, stu.id), "readiness": pathsvc.career_readiness(g, set(rows), done, vec, n, prof.career_goal),
        "review": rv})


@router.get("/plan.pdf")
def plan_pdf(user: User = Depends(student), db: Session = Depends(get_db)):
    return Response(plan_report(db, user), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="CometPath-plan-{user.full_name.replace(" ", "_")}.pdf"'})


# ── Advisor workspace ──────────────────────────────────────────────────────────
advising = APIRouter(prefix="/api/advising", tags=["advising"])
advisor = require_roles("advisor")


def _student(db: Session, user: User, sid: str) -> User:
    s = db.get(User, sid)
    if not s or s.org_id != user.org_id or s.role != "student":
        raise HTTPException(404, "Student not found")
    return s


@advising.get("/students")
def roster(status: str = "", user: User = Depends(advisor), db: Session = Depends(get_db)):
    progs = {p.id: p.name for p in db.scalars(select(Program).where(Program.org_id == user.org_id))}
    out = []
    for u, prof in db.execute(select(User, StudentProfile).outerjoin(StudentProfile, StudentProfile.user_id == User.id)
                              .where(User.org_id == user.org_id, User.role == "student", User.is_active).order_by(User.full_name)).all():
        rv = _latest_review(db, u.id)
        st = rv.status if rv else "none"
        if status and st != status:
            continue
        pending_ev = db.scalar(select(func.count()).select_from(Evidence).where(Evidence.student_id == u.id, Evidence.status == "pending")) or 0
        out.append({"id": u.id, "name": u.full_name, "email": u.email, "program": progs.get(prof.program_id) if prof else None,
                    "career_goal": prof.career_goal if prof else None, "review_status": st,
                    "review_id": rv.id if rv else None, "submitted_at": rv.created_at if rv else None, "pending_evidence": pending_ev})
    order = {"submitted": 0, "changes_requested": 1, "approved": 2, "none": 3}
    out.sort(key=lambda x: (order[x["review_status"]], x["name"]))
    return out


@advising.get("/students/{sid}")
def student_detail(sid: str, user: User = Depends(advisor), db: Session = Depends(get_db)):
    s = _student(db, user, sid)
    prof, rows = pathsvc.student_state(db, s.id)
    prof = prof or StudentProfile(user_id=s.id)
    g = pathsvc.load_graph(db, user.org_id)
    vec, n = pathsvc.career_vector(db, prof.career_goal, user.org_id)
    done = {cid for cid, sc in rows.items() if sc.status in pathsvc.TAKEN}
    rv = _latest_review(db, s.id)
    return {"student": {"id": s.id, "name": s.full_name, "email": s.email}, "profile": _profile_out(prof),
            "progress": pathsvc.progress(db, prof, rows, g) if prof.program_id else {"program": None},
            "courses": _courses(rows), "saved_plan": pathsvc.saved_plan(db, s.id),
            "readiness": pathsvc.career_readiness(g, set(rows), done, vec, n, prof.career_goal),
            "evidence": [{"id": e.id, "title": e.title, "kind": e.kind, "status": e.status, "bonus_points": e.bonus_points}
                         for e in db.scalars(select(Evidence).where(Evidence.student_id == s.id))],
            "review": _review_out(rv, db), "snapshot": rv.snapshot if rv else None}


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|changes_requested)$")
    note: str | None = Field(None, max_length=4000)


@advising.post("/reviews/{rid}")
def decide(rid: str, body: DecisionIn, user: User = Depends(advisor), db: Session = Depends(get_db)):
    r = db.get(PlanReview, rid)
    if not r or r.org_id != user.org_id:
        raise HTTPException(404, "Review not found")
    if body.decision == "changes_requested" and not (body.note or "").strip():
        raise HTTPException(400, "Explain which changes are needed")
    r.status, r.advisor_note, r.advisor_id, r.reviewed_at = body.decision, body.note, user.id, datetime.now(timezone.utc)
    audit(db, user, f"path.review.{body.decision}", student=r.student.email)
    notify(db, r.student, f"path.review.{body.decision}",
           "Your degree plan was approved" if body.decision == "approved" else "Your advisor requested changes to your plan",
           f"{user.full_name}: {body.note}" if body.note else f"Reviewed by {user.full_name}.", "/path")
    db.commit()
    return _review_out(r, db)


@advising.get("/students/{sid}/plan.pdf")
def student_plan_pdf(sid: str, user: User = Depends(advisor), db: Session = Depends(get_db)):
    s = _student(db, user, sid)
    return Response(plan_report(db, s), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="CometPath-plan-{s.full_name.replace(" ", "_")}.pdf"'})


@router.get("/saved")
def saved(user: User = Depends(student), db: Session = Depends(get_db)):
    """The student's saved semester plan, grouped by term."""
    return pathsvc.saved_plan(db, user.id)
