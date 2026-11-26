"""Handshake: the career center's job postings for the institution's students.

Handshake has no open jobs API, so CometIQ reads the jobs export career-center staff can download from Handshake
(CSV or Excel), uploaded by an admin, or the same export served from a URL (HANDSHAKE_FEED_URL, pulled with the nightly
job sync). Column names are matched flexibly. Each import is a full snapshot: postings missing from it, or past their
expiration date, are closed, so the job market reflects what is open on Handshake today.
"""
import csv
import io
import re
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Job
from . import http

SOURCE = "handshake"
# CometIQ field → header names seen in Handshake exports (compared case- and punctuation-insensitively)
COLUMNS = {
    "external_id": ["job id", "id", "posting id", "job posting id", "jobs id"],
    "title": ["job title", "title", "position", "jobs title", "job name"],
    "company": ["employer", "employer name", "company", "organization", "employers name"],
    "location": ["location", "locations", "job location", "city", "location s", "job locations"],
    "employment_type": ["job type", "employment type", "type", "jobs job type"],
    "description": ["description", "job description", "jobs description"],
    "posted_at": ["posted date", "created at", "date posted", "posted at", "jobs created at", "apply start"],
    "expires_at": ["expiration date", "expires at", "apply end", "jobs expiration date", "deadline"],
    "url": ["url", "job url", "apply url", "link", "posting url"],
    "duration": ["duration", "employment duration", "job duration"],
}
TYPES = {"internship": "Internship", "full-time": "Full-time", "full time": "Full-time", "part-time": "Part-time",
         "part time": "Part-time", "co-op": "Internship", "fellowship": "Full-time", "on campus": "Part-time"}


class HandshakeError(Exception):
    pass


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (h or "").lower()).strip()


def map_headers(headers: list[str]) -> dict[str, str]:
    """CometIQ field → the export's header for it."""
    by_norm = {_norm(h): h for h in headers if h}
    out = {}
    for field, names in COLUMNS.items():
        for n in names:
            if n in by_norm:
                out[field] = by_norm[n]
                break
    missing = [f for f in ("external_id", "title") if f not in out]
    if missing:
        raise HandshakeError(f"The file needs a {' and a '.join(m.replace('external_id', 'Job ID') for m in missing)} column "
                             f"(found: {', '.join(h for h in headers if h)[:300]})")
    return out


def parse(filename: str, raw: bytes) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(raw), read_only=True, data_only=True).active
        rows = [[("" if v is None else v) for v in r] for r in ws.iter_rows(values_only=True)]
        if not rows:
            return []
        headers = [str(h).strip() for h in rows[0]]
        return [dict(zip(headers, r)) for r in rows[1:] if any(str(v).strip() for v in r)]
    if filename.lower().endswith(".json"):
        import json

        data = json.loads(raw.decode("utf-8-sig"))
        data = data.get("jobs") or data.get("data") or data.get("results") or [] if isinstance(data, dict) else data
        return [d for d in data if isinstance(d, dict)]
    text = raw.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _date(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip()
    for fmt in (None, "%m/%d/%Y", "%m/%d/%Y %H:%M", "%m/%d/%y", "%Y-%m-%d %H:%M:%S %Z", "%b %d, %Y"):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00")) if fmt is None else datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize(rows: list[dict]) -> tuple[list[dict], list[str]]:
    if not rows:
        return [], []
    cols = map_headers(list(rows[0].keys()))
    out, skipped = [], []
    template = get_settings().HANDSHAKE_JOB_URL
    for i, r in enumerate(rows, 2):
        get = lambda f: (str(r.get(cols[f], "")).strip() if f in cols and r.get(cols[f]) is not None else "")  # noqa: E731
        ext, title = get("external_id"), get("title")
        if not ext or not title:
            skipped.append(f"row {i}: no job id or title")
            continue
        kind = get("employment_type").lower()
        etype = next((v for k, v in TYPES.items() if k in kind), None) or ("Internship" if "intern" in title.lower() else None)
        out.append({"source": SOURCE, "external_id": ext[:120], "title": title[:300], "company": get("company")[:200] or None,
                    "location": get("location")[:200] or None, "employment_type": etype, "description": get("description") or None,
                    "posted_at": _date(r.get(cols["posted_at"])) if "posted_at" in cols else None,
                    "expires_at": _date(r.get(cols["expires_at"])) if "expires_at" in cols else None,
                    "url": get("url") or (template.format(id=ext) if template else None)})
    return out, skipped


def apply(db: Session, org_id: str, jobs: list[dict], full_snapshot: bool = True) -> dict:
    """Add new postings, update changed ones, reopen ones back in the export, close the rest."""
    from ..services import jobs as jobsvc

    now = datetime.now(timezone.utc)
    existing = {j.external_id: j for j in db.scalars(select(Job).where(Job.source == SOURCE, Job.org_id == org_id))}
    added = updated = reopened = expired = 0
    seen = set()
    for d in jobs:
        seen.add(d["external_id"])
        exp = d.pop("expires_at", None)
        is_open = not (exp and exp < now)
        j = existing.get(d["external_id"])
        if j is None:
            if not is_open:
                expired += 1
                continue
            jobsvc.upsert_job(db, d, org_id=org_id)
            added += 1
            continue
        changed = any(getattr(j, k) != d[k] for k in ("title", "company", "location", "description", "url") if d.get(k) is not None)
        if changed:
            for k in ("title", "company", "location", "description", "url"):
                if d.get(k) is not None:
                    setattr(j, k, d[k])
            if d.get("description"):
                jobsvc.set_job_skills(db, j, jobsvc.extract_job_skills(j.title, j.description or "", j.role_family)[0])
            updated += 1
        if is_open and not j.is_open:
            reopened += 1
        if not is_open and j.is_open:
            expired += 1
        j.is_open = is_open
    closed = 0
    if full_snapshot:
        gone = [k for k, j in existing.items() if k not in seen and j.is_open]
        if gone:
            closed = db.execute(update(Job).where(Job.source == SOURCE, Job.org_id == org_id, Job.external_id.in_(gone))
                                .values(is_open=False)).rowcount or 0
    db.commit()
    open_now = db.scalar(select(func.count()).select_from(Job).where(Job.source == SOURCE, Job.org_id == org_id, Job.is_open))
    return {"in_file": len(jobs), "added": added, "updated": updated, "reopened": reopened, "expired": expired,
            "closed_missing": closed, "open_now": open_now}


def import_file(db: Session, org_id: str, filename: str, raw: bytes) -> dict:
    jobs, skipped = normalize(parse(filename, raw))
    if not jobs:
        raise HandshakeError("No postings found in the file" + (f" ({skipped[0]})" if skipped else ""))
    return apply(db, org_id, jobs) | {"skipped": len(skipped), "skipped_examples": skipped[:5]}


def feed_enabled() -> bool:
    return bool(get_settings().HANDSHAKE_FEED_URL)


def home_org_id(db: Session) -> str | None:
    """The institution the feed belongs to (SSO_ORG_SLUG, else the first organization)."""
    from ..models import Organization

    slug = get_settings().SSO_ORG_SLUG
    org = db.scalar(select(Organization).where(Organization.slug == slug)) if slug else None
    org = org or db.scalar(select(Organization).order_by(Organization.created_at))
    return org.id if org else None


def pull_feed(db: Session, org_id: str) -> dict:
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.HANDSHAKE_FEED_TOKEN}"} if s.HANDSHAKE_FEED_TOKEN else {}
    with http(timeout=60) as c:
        r = c.get(s.HANDSHAKE_FEED_URL, headers=headers)
    if r.status_code != 200:
        raise HandshakeError(f"The Handshake feed returned {r.status_code}")
    ctype = r.headers.get("content-type", "")
    name = "feed.json" if "json" in ctype else "feed.xlsx" if "spreadsheet" in ctype else "feed.csv"
    return import_file(db, org_id, name, r.content)
