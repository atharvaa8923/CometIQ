"""Find or create the CometIQ account for an external sign-in (single sign-on, or a launch from Canvas).

Matching order: the provider's stable subject id, then the institutional email (links accounts created earlier with
a password). New accounts get the given role (never admin) and no usable password. An existing account's role is
never changed here: admins manage roles in CometIQ.
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Organization, StudentProfile, User, UserIdentity


class AccountError(Exception):
    """Shown to the person."""


def home_org(db: Session) -> Organization:
    slug = get_settings().SSO_ORG_SLUG
    org = db.scalar(select(Organization).where(Organization.slug == slug)) if slug else None
    org = org or db.scalar(select(Organization).order_by(Organization.created_at))
    if not org:
        raise AccountError("CometIQ is not set up yet")
    return org


def link_or_create(db: Session, *, provider: str, subject: str, email: str, name: str, role: str, netid: str | None,
                   auto_provision: bool, action: str) -> tuple[User, bool]:
    from ..routers.auth import _role_allowed
    from ..security import audit, hash_password

    if role == "admin":
        raise AccountError("Administrator access is granted in CometIQ, not by sign-in")
    ident = db.scalar(select(UserIdentity).where(UserIdentity.provider == provider, UserIdentity.subject == subject))
    user = db.get(User, ident.user_id) if ident else None
    created = False
    if user is None:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        if not auto_provision:
            raise AccountError("You don't have a CometIQ account yet. Ask your administrator to add you.")
        if not _role_allowed(role):
            raise AccountError("This CometIQ pilot is not open to your role yet")
        user = User(org_id=home_org(db).id, email=email, full_name=name, role=role,
                    password_hash="!sso:" + hash_password(secrets.token_urlsafe(24)))   # no usable password
        db.add(user)
        db.flush()
        if role == "student":
            db.add(StudentProfile(user_id=user.id))
        created = True
    if not user.is_active:
        raise AccountError("This account is disabled")
    if not _role_allowed(user.role):
        raise AccountError("This CometIQ pilot is currently open to faculty only")
    if ident is None:
        ident = UserIdentity(user_id=user.id, provider=provider, subject=subject)
        db.add(ident)
    ident.netid, ident.email, ident.last_login_at = netid, email, datetime.now(timezone.utc)
    audit(db, user, action, created=created, **({"netid": netid} if netid else {}))
    return user, created
