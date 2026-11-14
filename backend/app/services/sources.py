"""Live job sources. All optional; each returns normalized posting dicts."""
import csv
import hashlib
import html
import io
import logging
import re

import httpx

from ..config import get_settings
from ..data.taxonomy import classify_role

log = logging.getLogger("cometiq.sources")

GITHUB_LISTS = {
    "New-grad roles (SimplifyJobs)": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    "Internships (SimplifyJobs)": "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
}
_TD = re.compile(r"<td>(.*?)</td>", re.S)
_TAG = re.compile(r"<[^>]+>")
_HREF = re.compile(r'href="([^"]+)"')
_US = re.compile(r",\s*(A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b|remote|united states|\bSF\b|\bNYC\b|\busa?\b", re.I)


def fetch_github_list(name: str, url: str, limit: int = 150) -> list[dict]:
    """Parse a SimplifyJobs-style HTML table. Keeps only roles CometIQ can classify."""
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    out, last_company = [], None
    for row in r.text.split("<tr>")[1:]:
        cells = _TD.findall(row)
        if len(cells) < 4:
            continue
        company = html.unescape(_TAG.sub("", cells[0])).strip()
        if company in ("↳", "") and last_company:
            company = last_company
        last_company = company
        title = html.unescape(_TAG.sub("", cells[1])).strip()
        location = html.unescape(_TAG.sub(" ", cells[2])).strip()
        if "🔒" in row or not title:
            continue  # closed posting
        if not _US.search(location):
            continue  # US roles only
        family = classify_role(title)
        if not family:
            continue
        links = _HREF.findall(cells[3])
        ext = hashlib.sha1(f"{company}|{title}|{location}".encode()).hexdigest()[:20]
        out.append({"title": title, "company": company, "location": " ".join(location.split())[:200], "role_family": family,
                    "url": links[0] if links else None, "external_id": ext, "source": "github",
                    "employment_type": "Internship" if "intern" in name.lower() or "intern" in title.lower() else "Full-time"})
        if len(out) >= limit:
            break
    return out


def fetch_adzuna(query: str, where: str = "Dallas", pages: int = 1) -> list[dict]:
    s = get_settings()
    if not (s.ADZUNA_APP_ID and s.ADZUNA_APP_KEY):
        raise RuntimeError("Adzuna keys not configured (ADZUNA_APP_ID / ADZUNA_APP_KEY)")
    out = []
    for page in range(1, pages + 1):
        r = httpx.get(f"https://api.adzuna.com/v1/api/jobs/us/search/{page}", timeout=30, params={
            "app_id": s.ADZUNA_APP_ID, "app_key": s.ADZUNA_APP_KEY, "what": query, "where": where,
            "results_per_page": 50, "content-type": "application/json"})
        r.raise_for_status()
        for j in r.json().get("results", []):
            out.append({"title": j.get("title", ""), "company": (j.get("company") or {}).get("display_name"),
                        "location": (j.get("location") or {}).get("display_name"), "description": j.get("description"),
                        "url": j.get("redirect_url"), "external_id": str(j.get("id")), "source": "adzuna"})
    return out


def parse_csv(data: bytes) -> list[dict]:
    """CSV columns: title (required), company, location, description, url, employment_type, role_family."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="ignore")))
    rows = []
    for r in reader:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        if not r.get("title"):
            continue
        ext = hashlib.sha1("|".join(r.get(k, "") for k in ("title", "company", "location", "description")).encode()).hexdigest()[:20]
        rows.append({"title": r["title"], "company": r.get("company") or None, "location": r.get("location") or None,
                     "description": r.get("description") or None, "url": r.get("url") or None,
                     "employment_type": r.get("employment_type") or None, "role_family": r.get("role_family") or None,
                     "external_id": ext, "source": "csv"})
    return rows


def fetch_usajobs(query: str, location: str = "Dallas", limit: int = 50) -> list[dict]:
    """USAJobs Search API (federal jobs). Docs: https://developer.usajobs.gov/api-reference/get-api-search"""
    s = get_settings()
    if not (s.USAJOBS_API_KEY and s.USAJOBS_EMAIL):
        raise RuntimeError("USAJobs not configured (USAJOBS_API_KEY and USAJOBS_EMAIL)")
    r = httpx.get("https://data.usajobs.gov/api/search", timeout=30,
                  params={"Keyword": query, "LocationName": location, "ResultsPerPage": min(limit, 500)},
                  headers={"Host": "data.usajobs.gov", "User-Agent": s.USAJOBS_EMAIL, "Authorization-Key": s.USAJOBS_API_KEY})
    r.raise_for_status()
    out = []
    for item in (r.json().get("SearchResult") or {}).get("SearchResultItems") or []:
        d = item.get("MatchedObjectDescriptor") or {}
        details = (d.get("UserArea") or {}).get("Details") or {}
        desc = "\n\n".join(x for x in (details.get("JobSummary"), "Required qualifications:\n" + d["QualificationSummary"]
                                        if d.get("QualificationSummary") else None) if x)
        out.append({"title": d.get("PositionTitle", ""), "company": d.get("OrganizationName") or d.get("DepartmentName"),
                    "location": d.get("PositionLocationDisplay"), "description": desc or None,
                    "url": d.get("PositionURI"), "external_id": str(d.get("PositionID") or item.get("MatchedObjectId")),
                    "source": "usajobs"})
    return [x for x in out if x["title"]]
