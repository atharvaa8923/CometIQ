"""Job ingestion: normalize postings, classify role family, extract required/preferred skills."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES, SKILLS, classify_role

CATEGORY_OF = {name: cat for name, cat, _a, _e in SKILLS}
from ..models import Job, JobSkill
from . import skills as sk

_PREF = re.compile(r"(preferred|nice[\s-]to[\s-]have|bonus|desired|a plus|pluses)[^\n]*\n", re.I)


def extract_job_skills(title: str, description: str, role_family: str | None = None) -> tuple[dict[str, str], str]:
    """Return ({skill_name: 'required'|'preferred'}, engine)."""
    desc = description or ""
    m = _PREF.search(desc)
    req_text, pref_text = (desc[: m.start()], desc[m.start():]) if m else (desc, "")
    out: dict[str, str] = {}
    engine = "builtin"
    if len(desc) > 80:
        found, engine = sk.extract(f"{title}\n{desc}", kind="job posting")
        req_found = sk.extract_builtin(f"{title}\n{req_text}")
        pref_found = sk.extract_builtin(pref_text)
        for name, info in found.items():
            if name in req_found:
                out[name] = "required"
            elif name in pref_found:
                out[name] = "preferred"
            else:
                out[name] = info.get("importance", "required")
    _demote_alternatives(req_text, out)
    family = role_family or classify_role(title)
    if len(out) < 3 and family:  # title-only posting: assume the family profile
        for name in ROLE_FAMILIES[family]["skills"]:
            out.setdefault(name, "preferred")
    return out, engine


def _demote_alternatives(req_text: str, out: dict[str, str]) -> None:
    """'Tableau or Power BI': the skill written right after 'or' / '/' becomes preferred (it is an alternative)."""
    for line in req_text.splitlines():
        seps = [m.end() for m in re.finditer(r"\s+or\s+|\s*/\s*", line, re.I)]
        if not seps:
            continue
        for name in sk.extract_builtin(line):
            pos = _first_pos(line, name)
            if out.get(name) == "required" and any(0 <= pos - e <= 1 for e in seps) and pos > 0:
                before = [n for n in out if out[n] == "required" and _first_pos(line, n) < pos and CATEGORY_OF.get(n) == CATEGORY_OF.get(name)]
                if before:
                    out[name] = "preferred"


def _first_pos(line: str, skill: str) -> int:
    pats = next((p for n, p in sk._matchers() if n == skill), [])
    hits = [m.start() for p in pats if (m := p.search(line))]
    return min(hits, default=10_000)


def _parse_date(v):
    """ISO date/datetime (or a datetime) → aware datetime; None if missing/unparseable."""
    from datetime import datetime, timezone

    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def upsert_job(db: Session, data: dict, org_id: str | None = None, employer_id: str | None = None,
               skills_override: dict[str, str] | None = None) -> Job | None:
    ext = data.get("external_id")
    if ext and db.scalar(select(Job.id).where(Job.source == data.get("source", "manual"), Job.external_id == ext)):
        return None
    family = data.get("role_family") or classify_role(data["title"])
    job = Job(
        org_id=org_id, employer_id=employer_id, external_id=ext, source=data.get("source", "manual"),
        title=data["title"][:300], company=data.get("company"), location=data.get("location"),
        role_family=family, employment_type=data.get("employment_type") or "Full-time",
        description=data.get("description"), url=data.get("url"),
    )
    posted = _parse_date(data.get("posted_at"))
    if posted:
        job.posted_at = posted
    db.add(job)
    db.flush()
    set_job_skills(db, job, skills_override if skills_override is not None
                   else extract_job_skills(job.title, job.description or "", family)[0])
    return job


def set_job_skills(db: Session, job: Job, mapping: dict[str, str]) -> None:
    job.skills.clear()
    db.flush()
    ids = sk.skill_ids(db, mapping.keys())
    for name, imp in mapping.items():
        if name in ids:
            job.skills.append(JobSkill(skill_id=ids[name], importance=imp if imp in ("required", "preferred") else "required"))
