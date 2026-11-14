"""Industry demand: browse, add, import and sync job postings."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, User
from ..security import audit, current_user, require_roles
from ..services import jobs as jobsvc
from ..services import sources

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def job_out(j: Job, with_desc: bool = False) -> dict:
    d = {"id": j.id, "title": j.title, "company": j.company, "location": j.location, "role_family": j.role_family,
         "employment_type": j.employment_type, "source": j.source, "url": j.url, "is_open": j.is_open,
         "posted_at": j.posted_at, "employer_id": j.employer_id,
         "skills": [{"id": s.skill.id, "name": s.skill.name, "category": s.skill.category, "importance": s.importance} for s in j.skills]}
    if with_desc:
        d["description"] = j.description
    return d


def visible(user: User):
    return (Job.org_id == user.org_id) | Job.org_id.is_(None)


@router.get("")
def list_jobs(q: str = "", role_family: str = "", source: str = "", limit: int = 50, offset: int = 0,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Job).where(visible(user), Job.is_open)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.location.ilike(like)))
    if role_family:
        stmt = stmt.where(Job.role_family == role_family)
    if source:
        stmt = stmt.where(Job.source == source)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Job.posted_at.desc()).offset(offset).limit(min(limit, 200)))
    by_source = dict(db.execute(select(Job.source, func.count()).where(visible(user), Job.is_open).group_by(Job.source)).all())
    return {"total": total, "by_source": by_source, "items": [job_out(j) for j in rows]}


@router.get("/{jid}")
def get_job(jid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, jid)
    if not j or (j.org_id and j.org_id != user.org_id):
        raise HTTPException(404, "Job not found")
    return job_out(j, True)


class JobIn(BaseModel):
    title: str = Field(min_length=2)
    company: str | None = None
    location: str | None = None
    description: str | None = None
    url: str | None = None
    employment_type: str | None = None
    role_family: str | None = None


@router.post("", status_code=201)
def add_job(body: JobIn, user: User = Depends(require_roles("faculty")), db: Session = Depends(get_db)):
    """Faculty/admin add a market posting for analysis (employers post via CometMatch)."""
    j = jobsvc.upsert_job(db, {**body.model_dump(), "source": "manual"}, org_id=user.org_id)
    audit(db, user, "jobs.add", title=body.title)
    db.commit()
    return job_out(j)


@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...), user: User = Depends(require_roles("faculty")), db: Session = Depends(get_db)):
    rows = sources.parse_csv(await file.read())
    if not rows:
        raise HTTPException(400, "No rows with a 'title' column found")
    added = sum(1 for r in rows if jobsvc.upsert_job(db, r, org_id=user.org_id))
    audit(db, user, "jobs.import_csv", rows=len(rows), added=added)
    db.commit()
    return {"rows": len(rows), "added": added}


class SyncIn(BaseModel):
    source: str = "github"           # github | adzuna
    query: str = "business analyst"  # adzuna only
    where: str = "Dallas"
    limit: int = 120


@router.post("/sync")
def sync(body: SyncIn, user: User = Depends(require_roles("faculty")), db: Session = Depends(get_db)):
    try:
        if body.source == "github":
            rows = []
            for name, url in sources.GITHUB_LISTS.items():
                rows += sources.fetch_github_list(name, url, limit=body.limit // 2)
        elif body.source == "adzuna":
            rows = sources.fetch_adzuna(body.query, body.where)
        else:
            raise HTTPException(400, "Unknown source")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Could not reach {body.source}: {e}")
    added = sum(1 for r in rows if jobsvc.upsert_job(db, r))  # shared market data
    audit(db, user, "jobs.sync", source=body.source, fetched=len(rows), added=added)
    db.commit()
    return {"fetched": len(rows), "added": added}
