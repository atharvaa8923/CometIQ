"""Ask CometIQ: questions answered only from stored records, with citations (LangGraph agent)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import audit, require_roles
from ..services import ask as asksvc

router = APIRouter(prefix="/api/ask", tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("")
def ask(body: AskIn, user: User = Depends(require_roles("faculty")), db: Session = Depends(get_db)):
    out = asksvc.ask(db, user, body.question)
    audit(db, user, "ask", intent=out["intent"], sources=len(out["citations"]), engine=out["engine"])
    db.commit()
    return out


@router.get("/examples")
def examples(user: User = Depends(require_roles("faculty"))):
    return {"examples": asksvc.EXAMPLES, "intents": asksvc.INTENTS}
