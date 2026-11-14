from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, Organization, StudentProfile, User
from ..security import audit, hash_password, require_roles
from .dashboard import org_counts

router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_only = require_roles("admin")


@router.get("/org")
def org_info(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    o = db.get(Organization, user.org_id)
    return {"id": o.id, "name": o.name, "slug": o.slug, "join_code": o.join_code, "plan": o.plan, **org_counts(db, o.id)}


@router.get("/users")
def list_users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.org_id == user.org_id).order_by(User.created_at.desc()))
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "company": u.company,
             "is_active": u.is_active, "created_at": u.created_at} for u in rows]


class NewUser(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    role: str = Field(pattern="^(admin|faculty|student|employer|advisor)$")
    password: str = Field(min_length=8)
    company: str | None = None


@router.post("/users", status_code=201)
def create_user(body: NewUser, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "Email already registered")
    u = User(org_id=user.org_id, email=body.email.lower(), full_name=body.full_name, role=body.role,
             company=body.company, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    if u.role == "student":
        db.add(StudentProfile(user_id=u.id))
    audit(db, user, "user.create", email=u.email, role=u.role)
    db.commit()
    return {"id": u.id}


class PatchUser(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|faculty|student|employer|advisor)$")
    is_active: bool | None = None


@router.patch("/users/{uid}")
def patch_user(uid: str, body: PatchUser, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u or u.org_id != user.org_id:
        raise HTTPException(404, "User not found")
    if u.id == user.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "You cannot demote or disable yourself")
    if body.role:
        u.role = body.role
        if u.role == "student" and not db.get(StudentProfile, u.id):
            db.add(StudentProfile(user_id=u.id))
    if body.is_active is not None:
        u.is_active = body.is_active
    audit(db, user, "user.update", target=u.email, **body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}


@router.get("/audit")
def audit_log(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.user_id)
                      .where(AuditLog.org_id == user.org_id).order_by(AuditLog.id.desc()).limit(200)).all()
    return [{"id": a.id, "action": a.action, "user": e, "detail": a.detail, "at": a.created_at} for a, e in rows]


# ── Integrations: job sources, AI and Nebula health ───────────────────────────
from fastapi import BackgroundTasks  # noqa: E402

from ..db import SessionLocal  # noqa: E402
from ..models import SyncRun  # noqa: E402
from ..services import ai, nebula  # noqa: E402
from ..services import sync as syncsvc  # noqa: E402


def _run_out(r: SyncRun) -> dict:
    return {"id": r.id, "trigger": r.trigger, "status": r.status, "results": r.results, "started_at": r.started_at, "finished_at": r.finished_at}


@router.get("/integrations")
def integrations(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    from ..config import get_settings
    from ..models import Job

    s = get_settings()
    counts = dict(db.execute(select(Job.source, func.count()).where(Job.is_open).group_by(Job.source)).all())
    runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(10))
    return {"job_sources": {k: {**v, "open_jobs": counts.get(k, 0)} for k, v in syncsvc.configured_sources().items()},
            "jobs_by_source": counts, "nightly": {"enabled": s.JOB_SYNC_ENABLED, "hour_utc": s.JOB_SYNC_HOUR_UTC,
                                                  "location": s.JOB_SYNC_LOCATION, "expire_days": s.JOB_EXPIRE_DAYS},
            "runs": [_run_out(r) for r in runs],
            "ai": {"enabled": ai.enabled(), "model": s.AI_MODEL}, "nebula": {"enabled": nebula.enabled()}}


def _manual_sync(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(SyncRun, run_id)
        if run:
            syncsvc.run_sync(db, run)


@router.post("/jobs/sync-now", status_code=202)
def sync_now(bg: BackgroundTasks, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(SyncRun.id).where(SyncRun.status == "running")):
        raise HTTPException(409, "A sync is already running")
    run = syncsvc.start_run(db, "manual")
    audit(db, user, "jobs.sync_now")
    db.commit()
    bg.add_task(_manual_sync, run.id)
    return _run_out(run)


@router.post("/ai/test")
def ai_test(user: User = Depends(admin_only)):
    """One tiny Claude call to confirm the API key works."""
    from pydantic import BaseModel as _BM

    if not ai.enabled():
        return {"ok": False, "message": "ANTHROPIC_API_KEY is not set — CometIQ is using its built-in engine."}

    class _Ping(_BM):
        skills: list[str]

    res = ai.structured("Extract the skills named in the text.", "Text: SQL, Tableau and Python.", _Ping, effort="low", max_tokens=1000)
    if res is None:
        return {"ok": False, "message": "Claude call failed — check the server log for the API error (key, model access or network)."}
    return {"ok": True, "message": f"Claude responded with {len(res.skills)} skills: {', '.join(res.skills)}"}
