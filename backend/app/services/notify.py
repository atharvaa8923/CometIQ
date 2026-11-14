"""Create in-app notifications and queue matching emails."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Notification, User
from . import tasks


def notify(db: Session, user: User, kind: str, title: str, body: str, link: str | None = None, cta: str = "Open CometIQ") -> None:
    """Adds the notification to the session and queues an email (sent after the caller commits)."""
    db.add(Notification(user_id=user.id, kind=kind, title=title, body=body, link=link))
    if user.email_notifications and user.is_active:
        url = get_settings().APP_URL.rstrip("/") + (link or "/app")
        db.flush()
        tasks.enqueue(db, "email.send", {"to": user.email, "title": title, "paragraphs": [f"Hi {user.full_name.split()[0]},", body],
                                         "cta": cta, "url": url}, org_id=user.org_id, user_id=user.id)


def notify_role(db: Session, org_id: str, role: str, kind: str, title: str, body: str, link: str | None = None) -> None:
    for u in db.scalars(select(User).where(User.org_id == org_id, User.role == role, User.is_active)):
        notify(db, u, kind, title, body, link)
