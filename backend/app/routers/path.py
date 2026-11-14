"""CometPath API — student profile, degree progress, recommendations and plans."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES
from ..db import get_db
from ..models import Concentration, Course, Program, StudentCourse, StudentProfile, User
from ..security import audit, require_roles
from ..services import path as pathsvc

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
