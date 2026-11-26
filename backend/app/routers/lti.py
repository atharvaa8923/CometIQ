"""CometIQ inside Canvas (LTI 1.3): tool configuration, login initiation, launch, and the in-Canvas course page."""
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations import lti
from ..models import CanvasConnection, Course, CourseAssignment, GapDecision, GapReview, SkillBadge, Syllabus, User
from ..security import create_token, current_user

router = APIRouter(prefix="/api/lti", tags=["lti"])


def _page(title: str, msg: str, status: int = 400) -> HTMLResponse:
    """Launch errors are shown inside the Canvas frame, so they are a small page rather than JSON."""
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#1e293b}}h1{{font-size:1.2rem;color:#0f3d2e}}</style></head>
<body><h1>{escape(title)}</h1><p>{escape(msg)}</p></body></html>""", status_code=status)


@router.get("/config.json")
def config():
    """The JSON a Canvas admin pastes into a new LTI 1.3 developer key."""
    return lti.tool_config()


@router.api_route("/login", methods=["GET", "POST"], include_in_schema=False)
async def login(request: Request):
    if not lti.enabled():
        return _page("CometIQ is not connected to Canvas", "An administrator needs to finish the LTI setup.", 404)
    params = dict(request.query_params)
    if request.method == "POST":
        params |= {k: str(v) for k, v in (await request.form()).items()}
    try:
        return RedirectResponse(lti.login_redirect(params), status_code=302)
    except lti.LTIError as e:
        return _page("CometIQ could not start", str(e))


@router.post("/launch", include_in_schema=False)
async def launch(request: Request, db: Session = Depends(get_db)):
    if not lti.enabled():
        return _page("CometIQ is not connected to Canvas", "An administrator needs to finish the LTI setup.", 404)
    form = await request.form()
    if form.get("error"):
        return _page("Canvas did not complete the launch", str(form.get("error_description") or form.get("error"))[:300])
    try:
        claims = lti.verify_launch(db, str(form.get("id_token") or ""), str(form.get("state") or ""))
        user, course = lti.sign_in(db, claims)
        db.commit()
    except lti.LTIError as e:
        db.rollback()
        return _page("CometIQ could not open", str(e))
    nxt = f"/lti/course/{course['canvas_course_id']}?title={quote(course.get('title') or course.get('label') or '')}"
    return RedirectResponse(f"{lti.app_url()}/sso/complete#token={create_token(user)}&next={quote(nxt)}", status_code=303)


# ── The in-Canvas course page ──────────────────────────────────────────────────
@router.get("/course/{cid}")
def course_page(cid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What this Canvas course builds, from its latest CometIQ analysis. Faculty also see gaps and review progress;
    students see the skills, how often employers ask for them, the graded work that practices them, and their badges."""
    from ..services import badges as badgesvc

    if not cid.isdigit():
        raise HTTPException(400, "Not a Canvas course id")
    syl = db.scalar(select(Syllabus).where(Syllabus.org_id == user.org_id, Syllabus.canvas_course_id == cid)
                    .order_by(Syllabus.created_at.desc()))
    staff = user.role in ("faculty", "advisor", "admin")
    out = {"canvas_course_id": cid, "role": user.role, "staff": staff, "set_up": False}
    if staff:
        out["canvas_connected"] = bool(db.get(CanvasConnection, user.id))
        out["can_import"] = user.role == "faculty"
    if not syl or not syl.analyses:
        return out
    ga = syl.analyses[0]
    course = db.get(Course, syl.course_id) if syl.course_id else None
    rows = ga.result.get("skills", [])
    graded: dict[str, list[str]] = {}
    for a in db.scalars(select(CourseAssignment).where(CourseAssignment.syllabus_id == syl.id, CourseAssignment.graded)):
        for s in a.skills or []:
            graded.setdefault(s, []).append(a.name)
    basis = badgesvc.faculty_basis(db, user.org_id).get(syl.course_id or "", {}) if syl.course_id else {}
    builds = sorted(({"skill": r["name"], "category": r.get("category"), "status": r["status"], "demand_pct": round(100 * r["demand"]),
                      "job_count": r.get("job_count"), "graded_share": r.get("graded_share"), "graded_in": graded.get(r["name"], [])[:4],
                      "faculty_level": (basis.get(r["skill_id"]) or {}).get("level")}
                     for r in rows if r["status"] in ("covered", "partial")),
                    key=lambda x: (x["status"] != "covered", -x["demand_pct"]))
    out |= {"set_up": True, "syllabus_id": syl.id, "analysis_id": ga.id, "course": {"code": syl.code, "title": course.title if course else syl.title,
            "semester": syl.semester}, "target": ga.target, "job_count": ga.job_count, "builds": builds}
    if staff:
        reviewed = db.scalar(select(func.count()).select_from(GapReview).where(GapReview.analysis_id == ga.id)) or 0
        open_decisions = db.scalar(select(func.count()).select_from(GapDecision).where(GapDecision.syllabus_id == syl.id,
                                                                                         GapDecision.status.in_(("open", "drafted")))) or 0
        gaps = [{"skill": r["name"], "status": r["status"], "priority": r["priority"], "demand_pct": round(100 * r["demand"])}
                for r in sorted(rows, key=lambda r: (r["status"] != "missing", -r["demand"])) if r["status"] != "covered"][:6]
        out |= {"score": ga.score, "score_basis": ga.result.get("score_basis", "mentions"), "gaps": gaps, "reviewed": reviewed,
                "skills_total": len(rows), "open_decisions": open_decisions}
    else:
        mine = db.scalars(select(SkillBadge).where(SkillBadge.student_id == user.id, SkillBadge.course_id == syl.course_id,
                                                   SkillBadge.status == "active")) if syl.course_id else []
        out["my_badges"] = [{"skill": b.skill.name, "level": b.level} for b in mine]
    return out
