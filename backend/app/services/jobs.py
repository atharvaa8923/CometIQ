"""Job ingestion: normalize postings, classify role family, extract required/preferred skills."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import ROLE_FAMILIES, classify_role
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
    family = role_family or classify_role(title)
    if len(out) < 3 and family:  # title-only posting: assume the family profile
        for name in ROLE_FAMILIES[family]["skills"]:
            out.setdefault(name, "preferred")
    return out, engine


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
