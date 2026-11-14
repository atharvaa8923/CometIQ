"""Background task handlers (imported by the worker)."""
from sqlalchemy.orm import Session

from ..models import Task
from . import email as mail
from .tasks import handler


@handler("email.send")
def send_email(db: Session, task: Task) -> dict:
    p = task.payload
    html_body, text = mail.render(p["title"], p.get("paragraphs", []), p.get("cta"), p.get("url"))
    mail.send(p["to"], p.get("subject") or p["title"], html_body, text)
    return {"sent_to": p["to"]}


@handler("gap.analyze")
def gap_analyze(db: Session, task: Task) -> dict:
    from ..routers.gap import run_analysis

    p = task.payload
    return run_analysis(db, p["syllabus_id"], p.get("target", "auto"), p.get("top_n", 30), p.get("extract", False), task)


@handler("forge.generate")
def forge_generate(db: Session, task: Task) -> dict:
    from ..models import User
    from ..routers.forge import GenerateIn, run_generate

    p = dict(task.payload)
    user = db.get(User, p.pop("user_id"))
    return run_generate(db, user, GenerateIn(**p), task)
