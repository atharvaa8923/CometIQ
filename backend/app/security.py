"""Password hashing, JWT tokens and role-based access dependencies."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuditLog, User

settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "ims": int(datetime.now(timezone.utc).timestamp() * 1000),  # ms issue time, for revocation on password change
        "sub": user.id,
        "org": user.org_id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    changed = user.password_changed_at
    if changed is not None:
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=timezone.utc)
        if payload.get("ims", 0) < int(changed.timestamp() * 1000):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired — please sign in again")
    from .services.tasks import current_org

    current_org.set(user.org_id)  # used by the AI usage cap
    return user


def require_roles(*roles: str):
    """Dependency factory: allow only the given roles (admins are always allowed)."""

    def dep(user: User = Depends(current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user

    return dep


def audit(db: Session, user: User | None, action: str, **detail) -> None:
    db.add(AuditLog(org_id=user.org_id if user else None, user_id=user.id if user else None,
                    action=action, detail=detail or None))
