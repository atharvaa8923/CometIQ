"""Versioned inputs for CometGap so reports stay reproducible and changes over time can be explained.

Every analysis records:
  - the syllabus version (text + the skills extracted from it),
  - the job sample (a frozen snapshot of each posting's skills, source and date),
  - the catalog version of the course,
  - the scoring version and the skill-taxonomy version.

`recompute` scores any recorded inputs with any registered scoring version. `compare` uses that to split the change
between two reports into: course revision (syllabus), demand change (job sample) and method update (scoring/taxonomy).
"""
import difflib
import hashlib
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import SKILLS
from ..models import CatalogVersion, Course, GapAnalysis, Job, JobSample, Program, Skill, Syllabus, SyllabusVersion

# Bump when the scoring formula changes, and keep the old function in SCORERS so older reports can still be recomputed.
SCORING_VERSION = "2026.11"
IMPORTANCE_W = {"required": 1.0, "preferred": 0.5}
STATUS_W = {"covered": 1.0, "partial": 0.5, "missing": 0.0}


def _hash(obj) -> str:
    data = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def taxonomy_version() -> str:
    """Changes whenever a skill, category or alias in the taxonomy changes (alias changes alter extraction)."""
    return _hash([[n, c, sorted(a)] for n, c, a, _ in SKILLS])[:12]


def _day(d) -> str | None:
    if d is None:
        return None
    return d.date().isoformat() if isinstance(d, datetime) else str(d)[:10]


# ── Syllabus versions ──────────────────────────────────────────────────────────
def skills_snapshot(syl: Syllabus) -> dict:
    return {ss.skill.name: {"mentions": ss.mentions, "excerpts": ss.excerpts or ([ss.evidence] if ss.evidence else [])}
            for ss in syl.skills}


def latest_version(db: Session, syllabus_id: str) -> SyllabusVersion | None:
    return db.scalar(select(SyllabusVersion).where(SyllabusVersion.syllabus_id == syllabus_id)
                     .order_by(SyllabusVersion.version.desc()).limit(1))


def ensure_version(db: Session, syl: Syllabus, user_id: str | None = None, engine: str = "builtin",
                   change_note: str | None = None) -> SyllabusVersion:
    """The version matching the syllabus as it is now; creates one if the text or extracted skills changed."""
    skills = skills_snapshot(syl)
    text_hash = _hash(syl.raw_text or "")
    last = latest_version(db, syl.id)
    if last and last.text_hash == text_hash and last.skills == skills and last.semester == syl.semester:
        return last
    v = SyllabusVersion(syllabus_id=syl.id, version=(last.version + 1) if last else 1, semester=syl.semester, filename=syl.filename,
                        raw_text=syl.raw_text or "", text_hash=text_hash, topics=list(syl.topics or []), skills=skills,
                        extraction_engine=engine, taxonomy_version=taxonomy_version(), change_note=change_note, created_by=user_id)
    db.add(v)
    db.flush()
    return v


# ── Job samples ────────────────────────────────────────────────────────────────
def snapshot_jobs(db: Session, job_ids: list[str]) -> dict:
    snap: dict[str, dict] = {}
    for j in db.scalars(select(Job).where(Job.id.in_(job_ids))) if job_ids else []:
        snap[j.id] = {"source": j.source, "posted": _day(j.posted_at), "role": j.role_family,
                      "skills": sorted([s.skill.name, s.importance] for s in j.skills)}
    return snap


def ensure_snapshot(db: Session, sample: JobSample) -> dict:
    """Older samples stored only posting IDs: snapshot them from the current postings the first time they are used."""
    if sample.snapshot is None:
        sample.snapshot = snapshot_jobs(db, list(sample.job_ids))
        sample.content_hash = _hash(sample.snapshot)
        db.flush()
    return sample.snapshot


def auto_sample(db: Session, org_id: str, target: str, job_ids: list[str]) -> JobSample:
    """Freeze the live postings an analysis used. Identical snapshots are shared between analyses."""
    snap = snapshot_jobs(db, job_ids)
    h = _hash(snap)
    existing = db.scalar(select(JobSample).where(JobSample.org_id == org_id, JobSample.kind == "auto", JobSample.content_hash == h).limit(1))
    if existing:
        return existing
    smp = JobSample(org_id=org_id, kind="auto", name=f"{target} postings, {datetime.now().date().isoformat()}",
                    method=f"Automatic snapshot of all open {target} postings visible to the institution when the analysis ran.",
                    criteria={"role_family": target, "status": "open"}, job_ids=sorted(snap), snapshot=snap, content_hash=h)
    db.add(smp)
    db.flush()
    return smp


def snapshot_summary(snap: dict) -> dict:
    sources: dict[str, int] = defaultdict(int)
    roles: dict[str, int] = defaultdict(int)
    dates = [v["posted"] for v in snap.values() if v.get("posted")]
    for v in snap.values():
        sources[v["source"]] += 1
        roles[v.get("role") or "Unclassified"] += 1
    return {"total": len(snap), "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
            "role_families": dict(sorted(roles.items(), key=lambda kv: -kv[1])),
            "date_from": min(dates) if dates else None, "date_to": max(dates) if dates else None}


def skill_meta(db: Session) -> dict[str, dict]:
    return {s.name: {"skill_id": s.id, "category": s.category, "is_emerging": s.is_emerging} for s in db.scalars(select(Skill))}


def demand_from_snapshot(snap: dict, meta: dict[str, dict]) -> tuple[list[dict], int]:
    """Same output as gap.market_demand, computed only from the frozen snapshot."""
    n = len(snap)
    if not n:
        return [], 0
    agg: dict[str, dict] = {}
    for job in snap.values():
        for name, imp in job["skills"]:
            if name not in meta:
                continue
            a = agg.setdefault(name, {"w": 0.0, "jobs": 0, "required": 0, "sources": defaultdict(int), "first": None, "last": None})
            a["w"] += IMPORTANCE_W.get(imp, 1.0)
            a["jobs"] += 1
            a["required"] += imp == "required"
            a["sources"][job["source"]] += 1
            p = job.get("posted")
            if p:
                a["first"] = min(a["first"], p) if a["first"] else p
                a["last"] = max(a["last"], p) if a["last"] else p
    out = []
    for name, a in agg.items():
        m = meta[name]
        out.append({"skill_id": m["skill_id"], "name": name, "category": m["category"], "is_emerging": m["is_emerging"],
                    "demand": round(a["w"] / n, 4), "job_count": a["jobs"], "job_share": round(a["jobs"] / n, 4),
                    "required_share": round(a["required"] / max(a["jobs"], 1), 4),
                    "required_count": a["required"], "preferred_count": a["jobs"] - a["required"],
                    "sources": dict(sorted(a["sources"].items(), key=lambda kv: -kv[1])),
                    "first_posted": a["first"], "last_posted": a["last"]})
    out.sort(key=lambda x: (-x["demand"], x["name"]))
    return out, n


# ── Scoring (pure, versioned) ──────────────────────────────────────────────────
def priority(demand: float) -> str:
    return "critical" if demand >= 0.40 else "high" if demand >= 0.25 else "medium" if demand >= 0.12 else "low"


def _score_2026_11(skills: dict, topics: list, demand: list[dict], top_n: int) -> tuple[list[dict], float]:
    """covered = ≥2 mentions or named in the schedule; partial = 1 mention; missing = none.
    Score = Σ demand × {1, 0.5, 0} / Σ demand over the top-N skills by demand."""
    topics_text = " ".join(topics or []).lower()
    rows = []
    for d in demand[:top_n]:
        ss = skills.get(d["name"])
        in_schedule = bool(ss) and d["name"].lower() in topics_text
        status = "missing" if not ss else "covered" if ss["mentions"] >= 2 or in_schedule else "partial"
        rows.append({**d, "status": status, "priority": priority(d["demand"]), "mentions": ss["mentions"] if ss else 0,
                     "evidence": (ss["excerpts"] or [None])[0] if ss else None, "excerpts": ss["excerpts"] if ss else [],
                     "in_schedule": in_schedule})
    total = sum(r["demand"] for r in rows) or 1
    return rows, round(100 * sum(r["demand"] * STATUS_W[r["status"]] for r in rows) / total, 1)


SCORERS = {"2026.11": _score_2026_11}


def score(skills: dict, topics: list, demand: list[dict], top_n: int, version: str | None = None) -> tuple[list[dict], float]:
    return SCORERS[version or SCORING_VERSION](skills, topics, demand, top_n)


# ── Catalog versions ───────────────────────────────────────────────────────────
def catalog_version(db: Session, org_id: str, code: str | None) -> CatalogVersion | None:
    if not code:
        return None
    c = db.scalar(select(Course).where(Course.org_id == org_id, Course.code == code))
    if not c:
        return None
    programs = []
    for p in db.scalars(select(Program).where(Program.org_id == org_id)):
        codes = {pc.course.code for pc in p.core} | {cc.course.code for conc in p.concentrations for cc in conc.courses}
        if code in codes:
            programs.append({"name": p.name, "catalog_year": p.catalog_year, "confirmed_by": p.catalog_confirmed_by,
                             "core": code in {pc.course.code for pc in p.core}})
    from ..models import CoursePrereq

    prereqs = db.execute(select(CoursePrereq.group, Course.code).join(Course, Course.id == CoursePrereq.requires_id)
                         .where(CoursePrereq.course_id == c.id)).all()
    snap = {"code": c.code, "title": c.title, "description": c.description or "", "credits": c.credits,
            "prerequisites": sorted(f"{code} (group {g})" for g, code in prereqs),
            "programs": sorted(programs, key=lambda x: x["name"])}
    years = sorted({p["catalog_year"] for p in programs if p["catalog_year"]})
    h = _hash(snap)
    cv = db.scalar(select(CatalogVersion).where(CatalogVersion.org_id == org_id, CatalogVersion.course_code == code,
                                                CatalogVersion.content_hash == h).limit(1))
    if not cv:
        cv = CatalogVersion(org_id=org_id, course_code=code, catalog_year=", ".join(years) or None, content_hash=h, snapshot=snap)
        db.add(cv)
        db.flush()
    return cv


# ── Recompute, reproduce, compare ──────────────────────────────────────────────
def inputs_of(db: Session, ga: GapAnalysis) -> dict | None:
    """The recorded inputs of an analysis, or None for analyses made before versioning."""
    sv = db.get(SyllabusVersion, ga.syllabus_version_id) if ga.syllabus_version_id else None
    smp = db.get(JobSample, ga.sample_id) if ga.sample_id else None
    if not sv or not smp or not smp.snapshot or not ga.scoring_version:
        return None
    cv = db.get(CatalogVersion, ga.catalog_version_id) if ga.catalog_version_id else None
    return {"syllabus_version": sv, "sample": smp, "catalog_version": cv, "scoring_version": ga.scoring_version,
            "taxonomy_version": ga.taxonomy_version, "top_n": ga.top_n or 30}


def describe_inputs(db: Session, ga: GapAnalysis) -> dict:
    inp = inputs_of(db, ga)
    if not inp:
        return {"recorded": False}
    sv, smp, cv = inp["syllabus_version"], inp["sample"], inp["catalog_version"]
    return {"recorded": True,
            "syllabus": {"id": sv.id, "version": sv.version, "semester": sv.semester, "text_hash": sv.text_hash[:12],
                         "created_at": sv.created_at, "change_note": sv.change_note, "engine": sv.extraction_engine},
            "sample": {"id": smp.id, "kind": smp.kind, "name": smp.name, "hash": (smp.content_hash or "")[:12], **snapshot_summary(smp.snapshot)},
            "catalog": {"id": cv.id, "catalog_year": cv.catalog_year, "hash": cv.content_hash[:12], "title": cv.snapshot.get("title"),
                        "confirmed_by": next((p["confirmed_by"] for p in cv.snapshot.get("programs", []) if p.get("confirmed_by")), None)} if cv else None,
            "scoring_version": ga.scoring_version, "taxonomy_version": ga.taxonomy_version, "top_n": inp["top_n"],
            "current_scoring_version": SCORING_VERSION, "current_taxonomy_version": taxonomy_version()}


def _reextract(text: str) -> dict:
    from .skills import extract_builtin

    return {n: {"mentions": i["mentions"], "excerpts": i.get("excerpts") or []} for n, i in extract_builtin(text).items()}


def reproduce(db: Session, ga: GapAnalysis) -> dict:
    """Recompute an analysis from its recorded inputs with its recorded scoring version and compare with the stored report."""
    inp = inputs_of(db, ga)
    if not inp:
        return {"reproducible": False, "reason": "This report was created before inputs were versioned. Re-run it to record them."}
    if ga.scoring_version not in SCORERS:
        return {"reproducible": False, "reason": f"Scoring version {ga.scoring_version} is no longer available."}
    sv, meta = inp["syllabus_version"], skill_meta(db)
    demand, _ = demand_from_snapshot(inp["sample"].snapshot, meta)
    rows, sc = score(sv.skills, sv.topics, demand, inp["top_n"], ga.scoring_version)
    stored = {r["name"]: (r["status"], round(r["demand"], 4)) for r in ga.result.get("skills", [])}
    again = {r["name"]: (r["status"], round(r["demand"], 4)) for r in rows}
    diffs = [{"skill": n, "stored": stored.get(n), "recomputed": again.get(n)} for n in sorted(set(stored) | set(again)) if stored.get(n) != again.get(n)]
    out = {"reproducible": True, "exact": sc == ga.score and not diffs, "stored_score": ga.score, "recomputed_score": sc,
           "differences": diffs[:20], "scoring_version": ga.scoring_version}
    if ga.scoring_version != SCORING_VERSION or (ga.taxonomy_version and ga.taxonomy_version != taxonomy_version()):
        skills_now = _reextract(sv.raw_text) if ga.taxonomy_version != taxonomy_version() else sv.skills
        out["current_method_score"] = score(skills_now, sv.topics, demand, inp["top_n"], SCORING_VERSION)[1]
    return out


def _syllabus_diff(a: SyllabusVersion, b: SyllabusVersion, limit: int = 12) -> dict:
    if a.text_hash == b.text_hash:
        return {"changed": False, "added": [], "removed": [], "added_count": 0, "removed_count": 0}
    al = [" ".join(x.split()) for x in a.raw_text.splitlines() if x.strip()]
    bl = [" ".join(x.split()) for x in b.raw_text.splitlines() if x.strip()]
    added, removed = [], []
    for line in difflib.ndiff(al, bl):
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return {"changed": True, "added_count": len(added), "removed_count": len(removed), "added": added[:limit], "removed": removed[:limit]}


def _catalog_diff(a: CatalogVersion | None, b: CatalogVersion | None) -> dict:
    if not a or not b:
        return {"available": False}
    if a.content_hash == b.content_hash:
        return {"available": True, "changed": False, "catalog_year": b.catalog_year}
    sa, sb = a.snapshot, b.snapshot
    return {"available": True, "changed": True, "catalog_year_from": a.catalog_year, "catalog_year_to": b.catalog_year,
            "title_changed": sa.get("title") != sb.get("title"), "description_changed": sa.get("description") != sb.get("description"),
            "prerequisites_added": sorted(set(sb.get("prerequisites", [])) - set(sa.get("prerequisites", []))),
            "prerequisites_removed": sorted(set(sa.get("prerequisites", [])) - set(sb.get("prerequisites", []))),
            "programs_added": sorted({p["name"] for p in sb.get("programs", [])} - {p["name"] for p in sa.get("programs", [])}),
            "programs_removed": sorted({p["name"] for p in sa.get("programs", [])} - {p["name"] for p in sb.get("programs", [])})}


def attribute(a_stored: float, b_stored: float, a_cur: float, b_cur: float, b_syl_a_demand: float, a_syl_b_demand: float) -> dict:
    """Split the score change B − A into course revision, demand change and method update (see compare()).

    The parts are shown to one decimal; they are rounded so that the shown parts always add up to the shown total
    (the method part, usually 0, absorbs the rounding remainder; if it is exactly 0 the larger part does)."""
    revision = ((b_syl_a_demand - a_cur) + (b_cur - a_syl_b_demand)) / 2
    demand = ((a_syl_b_demand - a_cur) + (b_cur - b_syl_a_demand)) / 2
    method = (b_stored - b_cur) - (a_stored - a_cur)
    total = round(b_stored - a_stored, 1)
    parts = {"course_revision": round(revision, 1), "demand_change": round(demand, 1), "method_update": round(method, 1)}
    rest = round(total - sum(parts.values()), 1)
    if rest:
        key = "method_update" if parts["method_update"] else max(("course_revision", "demand_change"), key=lambda k: abs(parts[k]))
        parts[key] = round(parts[key] + rest, 1)
    return {"total": total, **parts}


def compare(db: Session, a: GapAnalysis, b: GapAnalysis) -> dict:
    """Explain the change from report A (earlier) to report B (later).

    All four combinations of {A, B syllabus} × {A, B demand} are scored with the current method, so:
      method effect   = (B stored − B with current method) − (A stored − A with current method)
      course revision = average effect of swapping the syllabus, over both demand samples (Shapley split)
      demand change   = average effect of swapping the job sample, over both syllabi
    The three parts add up exactly to B − A.
    """
    ia, ib = inputs_of(db, a), inputs_of(db, b)
    if not ia or not ib:
        return {"available": False, "reason": "One of these reports was created before inputs were versioned. Re-run it to record them."}
    meta, tax = skill_meta(db), taxonomy_version()
    sva, svb = ia["syllabus_version"], ib["syllabus_version"]
    # skills under the current taxonomy (re-extract only when the taxonomy changed since that version was saved)
    ska = sva.skills if sva.taxonomy_version == tax else _reextract(sva.raw_text)
    skb = svb.skills if svb.taxonomy_version == tax else _reextract(svb.raw_text)
    da, _ = demand_from_snapshot(ia["sample"].snapshot, meta)
    dbm, _ = demand_from_snapshot(ib["sample"].snapshot, meta)
    na, nb = ia["top_n"], ib["top_n"]

    def s(skills, topics, demand, n):
        return score(skills, topics, demand, n, SCORING_VERSION)

    (ra_cur, A_cur), (_, B_cur) = s(ska, sva.topics, da, na), s(skb, svb.topics, dbm, nb)
    _, sB_dA = s(skb, svb.topics, da, na)
    _, sA_dB = s(ska, sva.topics, dbm, nb)
    effects = attribute(a.score, b.score, A_cur, B_cur, sB_dA, sA_dB)
    total = effects.pop("total")

    # per-skill changes with the reason for each
    stored_a = {r["name"]: r for r in a.result.get("skills", [])}
    stored_b = {r["name"]: r for r in b.result.get("skills", [])}
    rows_a_cur = {r["name"]: r for r in ra_cur}
    rows_bsyl_adem = {r["name"]: r for r in s(skb, svb.topics, da, na)[0]}
    skills = []
    for name in sorted(set(stored_a) | set(stored_b)):
        ra, rb = stored_a.get(name), stored_b.get(name)
        reasons = []
        if ra and rb:
            if ra["status"] != rb["status"]:
                if rows_bsyl_adem.get(name, {}).get("status") != rows_a_cur.get(name, {}).get("status"):
                    reasons.append("course revision")
                if ra["status"] != rows_a_cur.get(name, {}).get("status"):
                    reasons.append("method update")
            if abs(rb["demand"] - ra["demand"]) >= 0.05 or ra["priority"] != rb["priority"]:
                reasons.append("demand change")
        else:
            reasons.append("demand change")  # entered or left the top skills of the job sample
        if not reasons:
            continue
        skills.append({"skill": name, "status_from": ra["status"] if ra else None, "status_to": rb["status"] if rb else None,
                       "demand_from": ra["demand"] if ra else None, "demand_to": rb["demand"] if rb else None,
                       "priority_from": ra["priority"] if ra else None, "priority_to": rb["priority"] if rb else None,
                       "mentions_from": ska.get(name, {}).get("mentions", 0), "mentions_to": skb.get(name, {}).get("mentions", 0),
                       "in_top_from": ra is not None, "in_top_to": rb is not None, "reasons": reasons})
    order = {"course revision": 0, "method update": 1, "demand change": 2}
    skills.sort(key=lambda x: (order[x["reasons"][0]], x["skill"]))

    snap_a, snap_b = ia["sample"].snapshot, ib["sample"].snapshot
    return {
        "available": True,
        "from": {"analysis_id": a.id, "score": a.score, "created_at": a.created_at, "syllabus_version": sva.version, "semester": sva.semester},
        "to": {"analysis_id": b.id, "score": b.score, "created_at": b.created_at, "syllabus_version": svb.version, "semester": svb.semester},
        "total": total,
        "effects": effects,
        "method": {"scoring_from": a.scoring_version, "scoring_to": b.scoring_version, "taxonomy_from": a.taxonomy_version,
                   "taxonomy_to": b.taxonomy_version, "current_scoring": SCORING_VERSION, "current_taxonomy": tax},
        "syllabus": {"same_version": sva.id == svb.id, **_syllabus_diff(sva, svb)},
        "sample": {"same": ia["sample"].content_hash == ib["sample"].content_hash,
                   "from": {"name": ia["sample"].name, "kind": ia["sample"].kind, **snapshot_summary(snap_a)},
                   "to": {"name": ib["sample"].name, "kind": ib["sample"].kind, **snapshot_summary(snap_b)},
                   "postings_in_both": len(set(snap_a) & set(snap_b))},
        "catalog": _catalog_diff(ia["catalog_version"], ib["catalog_version"]),
        "skills": skills,
    }
