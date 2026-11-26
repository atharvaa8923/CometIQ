"""Canvas LMS for faculty: connect, list your courses, import a course's syllabus and graded assignments."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..integrations import canvas
from ..models import CanvasConnection, CourseAssignment, Syllabus, User
from ..security import audit, require_roles
from ..services import tasks

router = APIRouter(prefix="/api/canvas", tags=["canvas"])
faculty = require_roles("faculty")


def _conn(db: Session, user: User) -> CanvasConnection:
    if not canvas.enabled():
        raise HTTPException(404, "Canvas is not configured for this institution")
    conn = db.get(CanvasConnection, user.id)
    if not conn:
        raise HTTPException(400, "Connect your Canvas account first")
    return conn


@router.get("/status")
def status(user: User = Depends(faculty), db: Session = Depends(get_db)):
    conn = db.get(CanvasConnection, user.id) if canvas.enabled() else None
    return {"configured": canvas.enabled(), "connected": bool(conn), "canvas_name": conn.canvas_name if conn else None,
            "connected_at": conn.created_at if conn else None, "base_url": get_settings().CANVAS_BASE_URL or None}


@router.post("/connect")
def connect(user: User = Depends(faculty)):
    if not canvas.enabled():
        raise HTTPException(404, "Canvas is not configured for this institution")
    return {"url": canvas.authorize_url(user)}


@router.get("/callback", include_in_schema=False)
def callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    from urllib.parse import quote

    app = get_settings().APP_URL.rstrip("/")
    if error:
        return RedirectResponse(f"{app}/gap?canvas_error={quote('Canvas access was not granted' if error == 'access_denied' else error[:100])}", 303)
    try:
        uid = canvas.user_from_state(state)
        user = db.get(User, uid)
        if not user or not user.is_active:
            raise canvas.CanvasError("Sign in to CometIQ again, then connect Canvas")
        canvas.connect(db, uid, code)
        audit(db, user, "canvas.connected")
        db.commit()
    except canvas.CanvasError as e:
        db.rollback()
        return RedirectResponse(f"{app}/gap?canvas_error={quote(str(e))}", 303)
    return RedirectResponse(f"{app}/gap?canvas=connected", 303)


@router.delete("/connection")
def disconnect(user: User = Depends(faculty), db: Session = Depends(get_db)):
    conn = db.get(CanvasConnection, user.id)
    if conn:
        canvas.disconnect(db, conn)
        audit(db, user, "canvas.disconnected")
        db.commit()
    return {"connected": False}


@router.get("/courses")
def courses(user: User = Depends(faculty), db: Session = Depends(get_db)):
    try:
        return canvas.list_courses(db, user, _conn(db, user))
    except canvas.CanvasError as e:
        raise HTTPException(502, str(e))


class ImportIn(BaseModel):
    target: str = ""


@router.post("/courses/{cid}/import", status_code=202)
def import_course(cid: str, body: ImportIn | None = None, user: User = Depends(faculty), db: Session = Depends(get_db)):
    _conn(db, user)
    if not cid.isdigit():
        raise HTTPException(400, "Not a Canvas course id")
    t = tasks.enqueue(db, "canvas.import_course", {"canvas_course_id": cid}, user.org_id, user.id)
    return {"task_id": t.id, "status": t.status, **(t.result or {})}


@router.get("/syllabi/{sid}/assignments")
def assignments(sid: str, user: User = Depends(faculty), db: Session = Depends(get_db)):
    syl = db.get(Syllabus, sid)
    if not syl or syl.org_id != user.org_id:
        raise HTTPException(404, "Syllabus not found")
    rows = list(db.scalars(select(CourseAssignment).where(CourseAssignment.syllabus_id == sid)
                           .order_by(CourseAssignment.due_at.is_(None), CourseAssignment.due_at, CourseAssignment.name)))
    by_skill: dict[str, list[str]] = {}
    for a in rows:
        if a.graded:
            for s in a.skills or []:
                by_skill.setdefault(s, []).append(a.name)
    return {"canvas_course_id": syl.canvas_course_id,
            "assignments": [{"id": a.id, "name": a.name, "points": a.points, "due_at": a.due_at, "graded": a.graded,
                             "submission_types": a.submission_types, "skills": a.skills, "rubric": a.rubric,
                             "description": (a.description or "")[:600]} for a in rows],
            "graded_practice": dict(sorted(by_skill.items()))}
