"""Canvas LMS: faculty connect their Canvas account once; CometIQ imports a course's syllabus page and its graded
assignments (instructions and rubrics) and analyzes them like an uploaded syllabus.

Uses Canvas's OAuth2 flow with an institution developer key (scopes: read courses, syllabus and assignments) and the
REST API (https://canvas.instructure.com/doc/api/). Tokens are stored encrypted and refreshed automatically.
Re-importing the same Canvas course creates a new syllabus version only when its content changed.
"""
import re
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CanvasConnection, Course, CourseAssignment, Syllabus, User
from . import http
from .secrets import decrypt, encrypt

SEASONS = ("Spring", "Summer", "Fall", "Winter")
CODE = re.compile(r"\b([A-Z]{2,4})\s*-?\s*(\d{4})\b")


class CanvasError(Exception):
    pass


def enabled() -> bool:
    s = get_settings()
    return bool(s.CANVAS_BASE_URL and s.CANVAS_CLIENT_ID and s.CANVAS_CLIENT_SECRET)


def _base() -> str:
    return get_settings().CANVAS_BASE_URL.rstrip("/")


def redirect_uri() -> str:
    return f"{get_settings().APP_URL.rstrip('/')}/api/canvas/callback"


# ── OAuth2 ─────────────────────────────────────────────────────────────────────
def authorize_url(user: User) -> str:
    s = get_settings()
    state = jwt.encode({"aud": "cometiq-canvas", "uid": user.id, "exp": int(time.time()) + 600}, s.JWT_SECRET, algorithm="HS256")
    params = {"client_id": s.CANVAS_CLIENT_ID, "response_type": "code", "redirect_uri": redirect_uri(), "state": state}
    if s.CANVAS_SCOPES.strip():
        params["scope"] = " ".join(s.CANVAS_SCOPES.split())
    return f"{_base()}/login/oauth2/auth?" + urlencode(params)


def user_from_state(state: str) -> str:
    try:
        return jwt.decode(state, get_settings().JWT_SECRET, algorithms=["HS256"], audience="cometiq-canvas")["uid"]
    except jwt.PyJWTError:
        raise CanvasError("The Canvas connection request expired. Try again.")


def _token_request(data: dict) -> dict:
    s = get_settings()
    with http() as c:
        r = c.post(f"{_base()}/login/oauth2/token", data={"client_id": s.CANVAS_CLIENT_ID, "client_secret": s.CANVAS_CLIENT_SECRET,
                                                          "redirect_uri": redirect_uri(), **data})
    if r.status_code != 200 or "access_token" not in r.json():
        raise CanvasError("Canvas did not accept the authorization. Try connecting again.")
    return r.json()


def connect(db: Session, user_id: str, code: str) -> CanvasConnection:
    t = _token_request({"grant_type": "authorization_code", "code": code})
    conn = db.get(CanvasConnection, user_id) or CanvasConnection(user_id=user_id)
    conn.access_token, conn.refresh_token = encrypt(t["access_token"]), encrypt(t.get("refresh_token"))
    conn.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(t.get("expires_in") or 3600))
    conn.canvas_user_id = str((t.get("user") or {}).get("id") or "") or None
    conn.canvas_name = (t.get("user") or {}).get("name")
    db.add(conn)
    return conn


def _access_token(db: Session, conn: CanvasConnection) -> str:
    exp = conn.expires_at if not conn.expires_at or conn.expires_at.tzinfo else conn.expires_at.replace(tzinfo=timezone.utc)
    token = decrypt(conn.access_token)
    if token and exp and exp > datetime.now(timezone.utc) + timedelta(seconds=60):
        return token
    refresh = decrypt(conn.refresh_token)
    if not refresh:
        raise CanvasError("Your Canvas connection expired. Connect Canvas again.")
    t = _token_request({"grant_type": "refresh_token", "refresh_token": refresh})
    conn.access_token = encrypt(t["access_token"])
    conn.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(t.get("expires_in") or 3600))
    db.commit()
    return t["access_token"]


def disconnect(db: Session, conn: CanvasConnection) -> None:
    token = decrypt(conn.access_token)
    if token:
        try:   # best effort: revoke the token at Canvas too
            with http() as c:
                c.delete(f"{_base()}/login/oauth2/token", headers={"Authorization": f"Bearer {token}"})
        except Exception:
            pass
    db.delete(conn)


# ── REST API ───────────────────────────────────────────────────────────────────
def _get_all(db: Session, conn: CanvasConnection, path: str, params: dict | None = None, limit: int = 1000) -> list | dict:
    token = _access_token(db, conn)
    url, out = f"{_base()}/api/v1{path}", []
    with http() as c:
        while url and len(out) < limit:
            r = c.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
            params = None   # the next link already carries them
            if r.status_code == 401:
                raise CanvasError("Canvas refused the request. Connect Canvas again.")
            if r.status_code == 404:
                raise CanvasError("That Canvas course was not found, or you are not a teacher in it")
            if r.status_code >= 400:
                raise CanvasError(f"Canvas returned an error ({r.status_code})")
            data = r.json()
            if isinstance(data, dict):
                return data
            out += data
            url = r.links.get("next", {}).get("url")
    return out


def course_code(canvas_code: str | None, name: str | None = None) -> str | None:
    m = CODE.search((canvas_code or "").upper()) or CODE.search((name or "").upper())
    return f"{m.group(1)} {m.group(2)}" if m else None


def semester(term_name: str | None) -> str | None:
    if not term_name:
        return None
    season = next((x for x in SEASONS if x.lower() in term_name.lower()), None)
    year = re.search(r"(20\d{2})", term_name)
    return f"{season} {year.group(1)}" if season and year else term_name.strip()[:40]


def list_courses(db: Session, user: User, conn: CanvasConnection) -> list[dict]:
    rows = _get_all(db, conn, "/courses", {"enrollment_type": "teacher", "include[]": "term", "per_page": 50,
                                           "state[]": ["available", "completed", "unpublished"]})
    codes = {c.code.upper(): c for c in db.scalars(select(Course).where(Course.org_id == user.org_id))}
    imported = {s.canvas_course_id: s for s in db.scalars(select(Syllabus).where(Syllabus.org_id == user.org_id,
                                                                                  Syllabus.canvas_course_id.is_not(None)))}
    out = []
    for c in rows:
        code = course_code(c.get("course_code"), c.get("name"))
        cat = codes.get(code or "")
        syl = imported.get(str(c["id"]))
        out.append({"id": str(c["id"]), "name": c.get("name"), "course_code": c.get("course_code"), "state": c.get("workflow_state"),
                    "term": (c.get("term") or {}).get("name"), "semester": semester((c.get("term") or {}).get("name")),
                    "catalog_code": cat.code if cat else code, "in_catalog": bool(cat),
                    "imported_syllabus_id": syl.id if syl else None, "imported_semester": syl.semester if syl else None})
    return sorted(out, key=lambda x: (x["state"] != "available", x["name"] or ""))


# ── HTML → text ────────────────────────────────────────────────────────────────
class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "section", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(html: str | None) -> str:
    if not html:
        return ""
    p = _Text()
    p.feed(html)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip(" |") for ln in "".join(p.parts).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(ln for ln in lines)).strip()


# ── Import ─────────────────────────────────────────────────────────────────────
def fetch_course(db: Session, conn: CanvasConnection, cid: str) -> dict:
    course = _get_all(db, conn, f"/courses/{cid}", {"include[]": ["syllabus_body", "term"]})
    assignments = _get_all(db, conn, f"/courses/{cid}/assignments", {"per_page": 100, "order_by": "due_at"})
    return {"course": course, "assignments": assignments}


def assignment_rows(raw: list[dict]) -> list[dict]:
    from ..services.skills import extract_builtin

    out = []
    for a in raw:
        if a.get("published") is False:
            continue
        desc = html_text(a.get("description"))[:20000]
        rubric = [{"criterion": r.get("description") or "", "detail": r.get("long_description") or "", "points": r.get("points"),
                   "ratings": [x.get("description") for x in (r.get("ratings") or []) if x.get("description")][:6]}
                  for r in (a.get("rubric") or [])]
        rubric_text = "\n".join(f"{r['criterion']}: {r['detail']}" for r in rubric)
        graded = a.get("grading_type") != "not_graded" and not a.get("omit_from_final_grade") and (a.get("points_possible") or 0) > 0
        skills = sorted(extract_builtin(f"{a.get('name', '')}\n{desc}\n{rubric_text}"))
        out.append({"canvas_id": str(a["id"]), "name": (a.get("name") or "Untitled")[:300], "points": a.get("points_possible"),
                    "due_at": a.get("due_at"), "submission_types": a.get("submission_types") or [], "description": desc,
                    "rubric": rubric, "skills": skills, "graded": graded})
    return out


def compose_text(course: dict, assignments: list[dict]) -> str:
    """The text that is analyzed: the syllabus page, then every graded assignment with its rubric. Graded work counts
    as practice, so skills in assignments carry weight in the analysis."""
    parts = [f"{course.get('course_code') or ''} {course.get('name') or ''}".strip(), html_text(course.get("syllabus_body"))]
    graded = [a for a in assignments if a["graded"]]
    if graded:
        parts.append("GRADED ASSIGNMENTS")
        for a in graded:
            due = f", due {a['due_at'][:10]}" if a.get("due_at") else ""
            pts = f"{a['points']:g} points" if isinstance(a.get("points"), (int, float)) else "graded"
            parts.append(f"Assignment: {a['name']} ({pts}{due}) (graded)")
            if a["description"]:
                parts.append(a["description"][:4000])
            for r in a["rubric"]:
                parts.append(f"Rubric: {r['criterion']}" + (f" - {r['detail']}" if r["detail"] else ""))
    return "\n\n".join(p for p in parts if p).strip()


def import_course(db: Session, user: User, cid: str, task=None) -> dict:
    from ..services import parser
    from ..services import versions as vs
    from ..services.tasks import set_progress

    conn = db.get(CanvasConnection, user.id)
    if not conn:
        raise CanvasError("Connect Canvas first")
    if task:
        set_progress(db, task, "Reading the course from Canvas…")
    data = fetch_course(db, conn, cid)
    course, assignments = data["course"], assignment_rows(data["assignments"])
    text = compose_text(course, assignments)
    if len(text) < 80:
        raise CanvasError("This Canvas course has no syllabus page or graded assignments yet")
    code = course_code(course.get("course_code"), course.get("name"))
    cat = db.scalar(select(Course).where(Course.org_id == user.org_id, Course.code == code)) if code else None
    term = semester((course.get("term") or {}).get("name"))
    syl = db.scalar(select(Syllabus).where(Syllabus.org_id == user.org_id, Syllabus.canvas_course_id == str(cid)))
    created, changed = syl is None, True
    if syl is None:
        syl = Syllabus(org_id=user.org_id, owner_id=user.id, course_id=cat.id if cat else None, code=code or course.get("course_code"),
                       title=(cat.title if cat else course.get("name") or "Canvas course")[:300], semester=term,
                       filename=f"Canvas: {course.get('course_code') or cid}", raw_text=text, topics=parser.extract_topics(text),
                       canvas_course_id=str(cid))
        db.add(syl)
        db.flush()
    else:
        changed = (syl.raw_text or "") != text or (term and syl.semester != term)
        if changed:
            vs.ensure_version(db, syl, user_id=user.id)   # keep the version being replaced
            syl.raw_text, syl.topics, syl.filename = text, parser.extract_topics(text), f"Canvas: {course.get('course_code') or cid}"
            syl.semester = term or syl.semester
    existing = {a.canvas_id: a for a in db.scalars(select(CourseAssignment).where(CourseAssignment.syllabus_id == syl.id))}
    seen = set()
    for a in assignments:
        row = existing.get(a["canvas_id"]) or CourseAssignment(org_id=user.org_id, syllabus_id=syl.id, canvas_id=a["canvas_id"])
        due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00")) if a.get("due_at") else None
        row.name, row.points, row.due_at, row.submission_types = a["name"], a["points"], due, a["submission_types"]
        row.description, row.rubric, row.skills, row.graded = a["description"], a["rubric"], a["skills"], a["graded"]
        db.add(row)
        seen.add(a["canvas_id"])
    for k, row in existing.items():
        if k not in seen:
            db.delete(row)
    db.commit()
    result = {"syllabus_id": syl.id, "created": created, "changed": bool(changed), "assignments": len(assignments),
              "graded_assignments": sum(a["graded"] for a in assignments), "course_code": syl.code, "semester": syl.semester}
    if created or changed or not syl.analyses:
        from ..routers.gap import run_analysis

        if task:
            set_progress(db, task, "Analyzing the syllabus and assignments…")
        last = syl.analyses[0] if syl.analyses else None
        result |= run_analysis(db, syl.id, last.target if last else "auto", extract=True, task=task, user_id=user.id,
                               change_note=None if created else "Re-imported from Canvas")
    else:
        result["analysis_id"] = syl.analyses[0].id
    return result
