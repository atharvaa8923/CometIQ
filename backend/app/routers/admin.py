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
