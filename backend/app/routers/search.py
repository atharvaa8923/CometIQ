"""Search across courses, job postings and students.

PostgreSQL: full-text search over the GIN expression indexes created in migration 0006, ranked with ts_rank, with prefix
matching so it works as you type. SQLite (development): every word must appear (case-insensitive LIKE).
Students are searchable only by roles that may see them: employers (students open to opportunities), advisors and admins.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Course, Job, StudentProfile, User
from ..security import current_user

router = APIRouter(prefix="/api", tags=["search"])
WORD = re.compile(r"[A-Za-z0-9]+")

# Written out literally so they match the index expressions in migration 0006 (a bound parameter would not use the index).
COURSE_VEC = literal_column("to_tsvector('english', coalesce(courses.code, '') || ' ' || coalesce(courses.title, '') || ' ' || coalesce(courses.description, ''))")
JOB_VEC = literal_column("to_tsvector('english', coalesce(jobs.title, '') || ' ' || coalesce(jobs.company, '') || ' ' || coalesce(jobs.description, ''))")
NAME_VEC = literal_column("to_tsvector('simple', coalesce(users.full_name, ''))")
PROFILE_VEC = literal_column("to_tsvector('english', coalesce(student_profiles.headline, '') || ' ' || coalesce(student_profiles.career_goal, ''))")


def _tsquery(config: str, words: list[str]):
    """Every word must match, as a prefix (search as you type). Each word is tried stemmed and unstemmed: the English
    stemmer turns a partial word like "analy" into "anali", which would no longer be a prefix of "analyst"."""
    from functools import reduce

    def one(w):
        q = func.to_tsquery(literal_column(f"'{config}'"), f"{w.lower()}:*")
        return q if config == "simple" else q.op("||")(func.to_tsquery(literal_column("'simple'"), f"{w.lower()}:*"))

    return reduce(lambda a, b: a.op("&&")(b), [one(w) for w in words])


def _like_all(cols, words):
    return and_(*[or_(*[func.lower(func.coalesce(c, "")).like(f"%{w.lower()}%") for c in cols]) for w in words])


@router.get("/search")
def search(q: str, type: str = "all", limit: int = 20, user: User = Depends(current_user), db: Session = Depends(get_db)):
    words = WORD.findall(q)[:8]
    if not words or len("".join(words)) < 2:
        raise HTTPException(400, "Type at least two letters or digits")
    if type not in ("all", "courses", "jobs", "students"):
        raise HTTPException(400, "type must be all, courses, jobs or students")
    limit = max(1, min(limit, 50))
    pg = db.get_bind().dialect.name == "postgresql"
    out: dict[str, list] = {}

    if type in ("all", "courses"):
        stmt = select(Course).where(Course.org_id == user.org_id)
        if pg:
            query = _tsquery("english", words)
            stmt = stmt.where(COURSE_VEC.op("@@")(query)).order_by(func.ts_rank(COURSE_VEC, query).desc(), Course.code)
        else:
            stmt = stmt.where(_like_all([Course.code, Course.title, Course.description], words)).order_by(Course.code)
        out["courses"] = [{"type": "course", "id": c.id, "title": f"{c.code} {c.title}", "subtitle": (c.description or "")[:140],
                           "link": "/catalog"} for c in db.scalars(stmt.limit(limit))]

    if type in ("all", "jobs"):
        stmt = select(Job).where(Job.is_open, (Job.org_id == user.org_id) | Job.org_id.is_(None))
        if pg:
            query = _tsquery("english", words)
            stmt = stmt.where(JOB_VEC.op("@@")(query)).order_by(func.ts_rank(JOB_VEC, query).desc(), Job.posted_at.desc())
        else:
            stmt = stmt.where(_like_all([Job.title, Job.company, Job.description], words)).order_by(Job.posted_at.desc())
        out["jobs"] = [{"type": "job", "id": j.id, "title": j.title, "subtitle": " · ".join(x for x in (j.company, j.location) if x),
                        "link": "/match" if user.role in ("student", "employer") else "/gap?tab=jobs"} for j in db.scalars(stmt.limit(limit))]

    if type in ("all", "students") and user.role in ("employer", "advisor", "admin"):
        stmt = (select(User, StudentProfile).join(StudentProfile, StudentProfile.user_id == User.id)
                .where(User.org_id == user.org_id, User.role == "student", User.is_active))
        if user.role == "employer":
            stmt = stmt.where(StudentProfile.open_to_match)
        if pg:
            sq, eq = _tsquery("simple", words), _tsquery("english", words)
            stmt = stmt.where(or_(NAME_VEC.op("@@")(sq), PROFILE_VEC.op("@@")(eq))).order_by(
                (func.ts_rank(NAME_VEC, sq) + func.ts_rank(PROFILE_VEC, eq)).desc(), User.full_name)
        else:
            stmt = stmt.where(_like_all([User.full_name, StudentProfile.headline, StudentProfile.career_goal], words)).order_by(User.full_name)
        out["students"] = [{"type": "student", "id": u.id, "title": u.full_name, "subtitle": p.headline or p.career_goal or "",
                            "link": "/match" if user.role == "employer" else "/advising"} for u, p in db.execute(stmt.limit(limit)).all()]
    return {"q": q, "engine": "postgres-fts" if pg else "like", "results": out}
