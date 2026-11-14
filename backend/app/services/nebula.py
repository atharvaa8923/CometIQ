"""UTD Nebula Labs API client — live course sections, professors and grade distributions.

Endpoint used: GET /course/sections/trends?subject_prefix=BUAN&course_number=6341 (header x-api-key).
It returns every section of the course across semesters with professor details and a
14-bucket grade distribution, so one cached call powers sections, professors and grades.
"""
import logging
import time
from collections import defaultdict

import httpx

from ..config import get_settings

log = logging.getLogger("cometiq.nebula")

# Order of Nebula's 14-element grade_distribution (UTD Trends convention)
GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F", "W"]
POINTS = [4.0, 4.0, 3.67, 3.33, 3.0, 2.67, 2.33, 2.0, 1.67, 1.33, 1.0, 0.67, 0.0]  # W excluded from GPA
SEASON = {"S": ("Spring", 0), "U": ("Summer", 1), "F": ("Fall", 2)}
TTL, ERROR_TTL = 6 * 3600, 300
_cache: dict[tuple[str, str], tuple[float, dict]] = {}


def enabled() -> bool:
    return bool(get_settings().NEBULA_API_KEY)


def _session(name: str) -> tuple[tuple[int, int], str]:
    """'25F' → ((2025, 2), 'Fall 2025')."""
    try:
        yy, s = int(name[:2]), name[2].upper()
        season, order = SEASON[s]
        return (2000 + yy, order), f"{season} {2000 + yy}"
    except (ValueError, IndexError, KeyError):
        return (0, 0), name or "Unknown term"


def _stats(dist: list[int]) -> dict:
    graded = dist[:13]
    n_graded, total = sum(graded), sum(dist)
    gpa = round(sum(c * p for c, p in zip(graded, POINTS)) / n_graded, 2) if n_graded else None
    return {"distribution": [{"grade": g, "count": c} for g, c in zip(GRADES, dist)], "students": total, "gpa": gpa,
            "a_rate": round(100 * sum(dist[:3]) / n_graded, 1) if n_graded else None,
            "w_rate": round(100 * dist[13] / total, 1) if total else None}


def _prof_name(p: dict) -> str:
    return " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x).strip()


def summarize(sections: list[dict]) -> dict:
    by_term: dict[tuple, list] = defaultdict(list)
    labels: dict[tuple, str] = {}
    overall = [0] * 14
    prof_dist: dict[str, list[int]] = defaultdict(lambda: [0] * 14)
    for s in sections:
        key, label = _session((s.get("academic_session") or {}).get("name", ""))
        labels[key] = label
        by_term[key].append(s)
        dist = list(s.get("grade_distribution") or [])
        if len(dist) == 14:
            overall = [a + b for a, b in zip(overall, dist)]
            for p in s.get("professor_details") or []:
                if _prof_name(p):
                    prof_dist[_prof_name(p)] = [a + b for a, b in zip(prof_dist[_prof_name(p)], dist)]
    terms = sorted(by_term, reverse=True)
    latest = terms[0] if terms else None

    def section_out(s: dict) -> dict:
        meetings = []
        for m in s.get("meetings") or []:
            loc = m.get("location") or {}
            meetings.append({"days": ", ".join(m.get("meeting_days") or []), "time": "–".join(x for x in (m.get("start_time"), m.get("end_time")) if x),
                             "location": " ".join(x for x in (loc.get("building"), loc.get("room")) if x), "modality": m.get("modality")})
        return {"section": s.get("section_number"), "professors": [_prof_name(p) for p in s.get("professor_details") or [] if _prof_name(p)],
                "instruction_mode": s.get("instruction_mode"), "meetings": meetings, "syllabus_uri": s.get("syllabus_uri") or None}

    profs = [{"name": n, **_stats(d)} for n, d in prof_dist.items() if sum(d) >= 10]
    profs.sort(key=lambda x: (-(x["gpa"] or 0), x["name"]))
    return {"terms_offered": [labels[t] for t in terms[:8]], "latest_term": labels[latest] if latest else None,
            "sections": sorted((section_out(s) for s in by_term[latest]), key=lambda x: x["section"] or "") if latest else [],
            "grades": _stats(overall) if sum(overall) else None, "professors": profs[:10], "section_count": len(sections)}


def course_live(subject: str, number: str) -> dict:
    """Live data for a course, cached. Never raises: returns {'available': False, 'reason': …} on problems."""
    if not enabled():
        return {"configured": False, "available": False, "reason": "Nebula API key not configured (NEBULA_API_KEY)."}
    key = (subject.upper(), number)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    s = get_settings()
    try:
        r = httpx.get(f"{s.NEBULA_BASE_URL.rstrip('/')}/course/sections/trends", params={"subject_prefix": key[0], "course_number": key[1]},
                      headers={"x-api-key": s.NEBULA_API_KEY, "Accept": "application/json"}, timeout=15)
        if r.status_code == 404:
            out = {"configured": True, "available": False, "reason": "Nebula has no sections for this course."}
        else:
            r.raise_for_status()
            sections = r.json().get("data") or []
            out = {"configured": True, "available": bool(sections), "source": "UTD Nebula Labs", "fetched_at": int(time.time()),
                   **summarize(sections)} if sections else {"configured": True, "available": False, "reason": "No sections found on Nebula."}
        _cache[key] = (time.time() + TTL, out)
        return out
    except Exception as e:  # network, auth, schema — degrade gracefully
        log.warning("Nebula request failed for %s %s: %s", *key, e)
        out = {"configured": True, "available": False, "reason": f"Nebula is unavailable right now ({type(e).__name__})."}
        _cache[key] = (time.time() + ERROR_TTL, out)
        return out
