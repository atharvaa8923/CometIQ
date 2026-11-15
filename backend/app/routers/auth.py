import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Organization, PasswordReset, StudentProfile, User
from ..schemas import LoginIn, RegisterIn, user_out
from ..security import audit, create_token, current_user, hash_password, verify_password
from ..services import tasks

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
    """Unauthenticated: tells the login/register pages whether demo accounts exist and which roles are open."""
    allowed = get_settings().allowed_roles()
    return {"demo": get_settings().SEED_DEMO, "pilot_roles": sorted(allowed) if allowed else None}


def _role_allowed(role: str) -> bool:
    allowed = get_settings().allowed_roles()
    return not allowed or role in allowed


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
    if not _role_allowed(user.role):
        raise HTTPException(403, "This CometIQ pilot is currently open to faculty only")
    if not user.is_active:
        raise HTTPException(403, "Account disabled")
    audit(db, user, "login")
    db.commit()
    return {"token": create_token(user), "user": user_out(user)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not _role_allowed(body.role if body.join_code else "admin"):
        raise HTTPException(403, "Registration for this role is closed during the pilot")
    if not body.accept_terms:
        raise HTTPException(400, "Please accept the privacy notice and terms of use")
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
    from .privacy import POLICY_VERSION

    user.consent_version, user.consent_at = POLICY_VERSION, datetime.now(timezone.utc)
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


# ── Password reset & account settings ─────────────────────────────────────────


class ForgotIn(BaseModel):
    email: str


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Always answers the same way so the endpoint can't be used to discover accounts."""
    key = (request.client.host if request.client else "?", "forgot:" + body.email.strip().lower())
    if _limited(key):
        raise HTTPException(429, "Too many requests. Try again later.")
    _failures.setdefault(key, []).append(time.time())  # counts toward the limit (max N emails per 15 min)
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower(), User.is_active))
    if user:
        s = get_settings()
        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=user.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                             expires_at=datetime.now(timezone.utc) + timedelta(minutes=s.PASSWORD_RESET_MINUTES)))
        audit(db, user, "auth.reset_requested")
        db.commit()
        tasks.enqueue(db, "email.send", {
            "to": user.email, "title": "Reset your CometIQ password",
            "paragraphs": [f"Hi {user.full_name.split()[0]},",
                           f"Someone asked to reset the password for your CometIQ account. The link works once and expires in {s.PASSWORD_RESET_MINUTES} minutes.",
                           "If this wasn't you, ignore this email — your password stays the same."],
            "cta": "Choose a new password", "url": f"{s.APP_URL.rstrip('/')}/reset-password?token={token}"},
            org_id=user.org_id, user_id=user.id)
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hashlib.sha256(body.token.encode()).hexdigest()))
    exp = pr.expires_at.replace(tzinfo=timezone.utc) if pr and pr.expires_at.tzinfo is None else (pr.expires_at if pr else None)
    if not pr or pr.used_at or exp < now:
        raise HTTPException(400, "This reset link is invalid or has expired. Request a new one.")
    user = db.get(User, pr.user_id)
    user.password_hash = hash_password(body.password)
    user.password_changed_at = now
    for other in db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))):
        other.used_at = now  # every outstanding link dies with this reset
    audit(db, user, "auth.password_reset")
    db.commit()
    return {"token": create_token(user), "user": user_out(user)}


class ChangePwIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/change-password")
def change_password(body: ChangePwIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    audit(db, user, "auth.password_changed")
    db.commit()
    return {"token": create_token(user)}  # other devices are signed out; this one gets a fresh token


class SettingsIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    email_notifications: bool | None = None


@router.patch("/me")
def update_me(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.full_name:
        user.full_name = body.full_name.strip()
    if body.email_notifications is not None:
        user.email_notifications = body.email_notifications
    db.commit()
    return user_out(user)
