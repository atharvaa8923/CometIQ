from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Task, User
from ..security import current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{tid}")
def get_task(tid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t or (t.user_id != user.id and not (user.role == "admin" and t.org_id == user.org_id)):
        raise HTTPException(404, "Task not found")
    return {"id": t.id, "kind": t.kind, "status": t.status, "progress": t.progress, "result": t.result,
            "error": _error(t) if t.status == "failed" else None,
            "created_at": t.created_at, "finished_at": t.finished_at}


def _error(t: Task) -> str:
    """Internal errors stay in the server log; messages written for people (TaskError) are shown as they are."""
    prefix = "TaskError: "
    return t.error[len(prefix):] if (t.error or "").startswith(prefix) else "The job failed. Please try again."
