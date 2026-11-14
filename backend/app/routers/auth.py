import re
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Organization, StudentProfile, User
from ..schemas import LoginIn, RegisterIn, user_out
from ..security import audit, create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


_failures: dict[tuple[str, str], list[float]] = {}
WINDOW = 15 * 60


def _limited(key: tuple[str, str]) -> bool:
    now = time.time()
    hits = [t for t in _failures.get(key, []) if now - t < WINDOW]
    _failures[key] = hits
    return len(hits) >= get_settings().LOGIN_RATE_LIMIT


@router.get("/public-config")
def public_config():
    """Unauthenticated: tells the login page whether demo accounts exist."""
    return {"demo": get_settings().SEED_DEMO}


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = (request.client.host if request.client else "?", body.email.strip().lower())
    if _limited(key):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        _failures.setdefault(key, []).append(time.time())
        raise HTTPException(401, "Invalid email or password")
    _failures.pop(key, None)
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    audit(db, user, "login")
    db.commit()
    return {"token": create_token(user), "user": user_out(user)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Email already registered")
    role = body.role
    if body.join_code:
        org = db.scalar(select(Organization).where(Organization.join_code == body.join_code.strip().upper()))
        if not org:
            raise HTTPException(404, "Invalid organization join code")
    elif body.org_name:
        slug = re.sub(r"[^a-z0-9]+", "-", body.org_name.lower()).strip("-")[:60] or "org"
        if db.scalar(select(Organization.id).where(Organization.slug == slug)):
            slug = f"{slug}-{secrets.token_hex(2)}"
        org = Organization(name=body.org_name.strip(), slug=slug, join_code=f"COMET-{secrets.token_hex(3).upper()}")
        db.add(org)
        db.flush()
        role = "admin"  # creator of a new organization administers it
    else:
        raise HTTPException(400, "Provide an organization join code or a new organization name")
    user = User(org_id=org.id, email=email, full_name=body.full_name.strip(), role=role,
                company=body.company, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    if role == "student":
        db.add(StudentProfile(user_id=user.id))
    audit(db, user, "register", role=role)
    db.commit()
    db.refresh(user)
    return {"token": create_token(user), "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
