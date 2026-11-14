from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, User
from ..security import current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(30))
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                                         "read": n.read_at is not None, "created_at": n.created_at} for n in rows]}


@router.post("/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True}
