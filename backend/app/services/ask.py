"""Ask CometIQ: a LangGraph agent that answers questions only from CometIQ's stored records, with citations.

Graph:  understand → (help | gather) → write → verify → END
  understand  decide what is being asked (Claude when configured, keyword rules otherwise) and pull out a course code / skill
  gather      run read-only, permission-scoped queries over the database; every fact becomes a numbered record with a link
  write       compose the answer from the records only (Claude when configured, a deterministic template otherwise)
  verify      drop citations that point to no record and attach the sources list; refuse to answer without records

Nothing is written to the database except an audit entry.
"""
import re
from typing import Literal, TypedDict

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, CurriculumProposal, GapDecision, Skill, SkillBadge, Syllabus, User
from . import ai
from . import versions as vs
from .skills import extract_builtin

INTENTS = {
    "score_change": "Why a course's coverage score changed between reports",
    "unimplemented": "Accepted curriculum changes that were never implemented",
    "overlap": "Skills the program teaches in several courses",
    "aacsb_summary": "An assurance-of-learning (AACSB) summary for one skill",
    "undecided_gaps": "Priority gaps nobody has decided on",
    "proposals": "Curriculum proposals waiting for review or recently decided",
    "where_taught": "Where a skill is introduced, practiced or mastered",
    "help": "Anything else: explain what Ask CometIQ can answer",
}
EXAMPLES = ["Why did BUAN 6356 drop?", "Which accepted changes were never implemented?", "Where does the program teach SQL twice?",
            "Draft the AACSB summary for SQL.", "Which priority gaps have no decision yet?", "Which proposals are waiting for review?",
            "Where is Python practiced?"]
CODE = re.compile(r"\b([A-Z]{2,4})\s?-?(\d{4})\b", re.I)


class State(TypedDict, total=False):
    question: str
    org_id: str
    user_id: str
    role: str
    intent: str
    course: str | None
    skill: str | None
    records: list[dict]
    answer: str
    citations: list[dict]
    engine: str
    steps: list[str]


# ── helpers ────────────────────────────────────────────────────────────────────
def _syllabi(db: Session, s: State, code: str | None = None) -> list[Syllabus]:
    q = select(Syllabus).where(Syllabus.org_id == s["org_id"])
    if s["role"] != "admin":
        q = q.where(Syllabus.owner_id == s["user_id"])
    if code:
        q = q.where(Syllabus.code.ilike(code))
    return list(db.scalars(q.order_by(Syllabus.created_at.desc())))


def _rec(records: list[dict], kind: str, title: str, link: str, facts: dict) -> int:
    records.append({"n": len(records) + 1, "type": kind, "title": title, "link": link, "facts": facts})
    return len(records)


def _skill_from(question: str) -> str | None:
    found = extract_builtin(question)
    return max(found, key=len) if found else None


def _course_from(question: str) -> str | None:
    m = CODE.search(question)
    return f"{m.group(1).upper()} {m.group(2)}" if m else None


# ── node: understand ───────────────────────────────────────────────────────────
class _Route(BaseModel):
    intent: Literal["score_change", "unimplemented", "overlap", "aacsb_summary", "undecided_gaps", "proposals", "where_taught", "help"]
    course_code: str | None = Field(None, description="Course code like 'BUAN 6356' if the question names one")
    skill: str | None = Field(None, description="Skill name if the question is about one skill")


def _rules(q: str) -> str:
    t = q.lower()
    if any(k in t for k in ("aacsb", "assurance of learning", "accreditation")):
        return "aacsb_summary"
    if any(k in t for k in ("twice", "overlap", "duplicate", "redundan", "more than one course", "several courses")):
        return "overlap"
    if any(k in t for k in ("never implemented", "not implemented", "unimplemented", "still open", "never got")):
        return "unimplemented"
    if any(k in t for k in ("drop", "fell", "decline", "went down", "rise", "rose", "went up", "increase", "change", "why did")) and _course_from(q):
        return "score_change"
    if "proposal" in t:
        return "proposals"
    if any(k in t for k in ("no decision", "undecided", "without a decision", "priority gap", "biggest gap", "top gap")):
        return "undecided_gaps"
    if any(k in t for k in ("where", "which course", "taught", "practiced", "mastered", "introduced")):
        return "where_taught"
    return "help"


def understand(s: State, db: Session) -> State:
    q = s["question"]
    course, skill, intent, engine = _course_from(q), _skill_from(q), _rules(q), "builtin"
    r = ai.structured(
        system=("You route questions for a university curriculum analytics tool. Pick the single intent that best matches. "
                "Extract a course code (e.g. 'BUAN 6356') and a skill name only if the question names them."),
        prompt="Intents:\n" + "\n".join(f"- {k}: {v}" for k, v in INTENTS.items()) + f"\n\nQuestion: {q}",
        schema=_Route, effort="low", max_tokens=2000)
    if r:
        intent, engine = r.intent, "claude"
        course = _course_from(r.course_code or "") or course
        if r.skill:
            known = {n.lower(): n for (n,) in db.execute(select(Skill.name))}
            skill = known.get(r.skill.strip().lower(), skill)
    if intent in ("aacsb_summary", "where_taught") and not skill:
        intent = "help"
    return {"intent": intent, "course": course, "skill": skill, "engine": engine, "steps": s.get("steps", []) + [f"understand → {intent}"]}


# ── node: gather (read-only tools) ─────────────────────────────────────────────
def _g_score_change(db: Session, s: State, R: list[dict]) -> None:
    for syl in _syllabi(db, s, s.get("course")):
        reports = [ga for ga in sorted(syl.analyses, key=lambda a: a.created_at) if vs.inputs_of(db, ga)]
        if len(reports) < 2:
            continue
        a, b = reports[-2], reports[-1]
        c = vs.compare(db, a, b)
        _rec(R, "comparison", f"{syl.code} coverage {a.score}% → {b.score}%", f"/gap/course/{syl.id}",
             {"course": syl.code, "from": f"{a.score}% on {a.created_at.date()} (syllabus v{c['from']['syllabus_version']})",
              "to": f"{b.score}% on {b.created_at.date()} (syllabus v{c['to']['syllabus_version']})", "total_change": c["total"],
              "course_revision": c["effects"]["course_revision"], "demand_change": c["effects"]["demand_change"],
              "method_update": c["effects"]["method_update"], "same_job_sample": c["sample"]["same"],
              "postings": f"{c['sample']['from']['total']} → {c['sample']['to']['total']}"})
        for x in c["skills"][:6]:
            _rec(R, "skill_change", f"{syl.code}: {x['skill']}", f"/gap/course/{syl.id}",
                 {"status": f"{x['status_from']} → {x['status_to']}", "share_of_postings": f"{round((x['demand_from'] or 0) * 100)}% → {round((x['demand_to'] or 0) * 100)}%",
                  "mentions": f"{x['mentions_from']} → {x['mentions_to']}", "why": ", ".join(x["reasons"])})
        return


def _g_unimplemented(db: Session, s: State, R: list[dict]) -> None:
    ids = {x.id: x for x in _syllabi(db, s, s.get("course"))}
    for d in db.scalars(select(GapDecision).where(GapDecision.syllabus_id.in_(list(ids)), GapDecision.decision == "add_here",
                                                  GapDecision.status.in_(("open", "drafted"))).order_by(GapDecision.decided_at)):
        syl = ids[d.syllabus_id]
        _rec(R, "decision", f"{syl.code}: add {d.skill.name}", f"/gap/course/{syl.id}?tab=decisions",
             {"decided": f"{d.decided_at.date()} by {d.reviewer_name or 'former faculty member'}", "status": d.status,
              "draft_linked": bool(d.forge_draft_id), "mention_signal_in_later_version": d.detected_in_version, "rationale": d.rationale})


def _faculty_levels(db: Session, org_id: str) -> dict[int, list[tuple[str, str, str]]]:
    """skill_id → [(course code, level, source)] from faculty confirmations (reviews and curriculum map)."""
    from .badges import faculty_basis

    codes = {c.id: c.code for c in db.scalars(select(Course).where(Course.org_id == org_id))}
    out: dict[int, list] = {}
    for cid, skills in faculty_basis(db, org_id).items():
        for sid, b in skills.items():
            out.setdefault(sid, []).append((codes.get(cid, "?"), "M" if b["level"] == "mastered" else "P", b["source"]))
    return out


def _g_overlap(db: Session, s: State, R: list[dict]) -> None:
    names = dict(db.execute(select(Skill.id, Skill.name)).all())
    for sid, rows in sorted(_faculty_levels(db, s["org_id"]).items(), key=lambda kv: -len(kv[1])):
        if len(rows) >= 2 and (not s.get("skill") or names.get(sid) == s["skill"]):
            _rec(R, "overlap", f"{names.get(sid)} practiced in {len(rows)} courses", "/curriculum?tab=map",
                 {"courses": ", ".join(f"{c} ({lvl}, {src})" for c, lvl, src in sorted(rows))})


def _g_where(db: Session, s: State, R: list[dict]) -> None:
    sk = db.scalar(select(Skill).where(Skill.name == s["skill"]))
    if not sk:
        return
    rows = _faculty_levels(db, s["org_id"]).get(sk.id, [])
    if rows:
        _rec(R, "faculty_levels", f"{sk.name}: faculty-confirmed courses", "/curriculum?tab=map",
             {"courses": ", ".join(f"{c} ({lvl}, {src})" for c, lvl, src in sorted(rows))})
    confirmed = {c for c, _, _ in rows}
    for syl in _syllabi(db, s)[:40]:
        ga = syl.analyses[0] if syl.analyses else None
        sv = db.get(vs.SyllabusVersion, ga.syllabus_version_id) if ga and ga.syllabus_version_id else None
        info = (sv.skills if sv else vs.skills_snapshot(syl)).get(sk.name)
        if info and syl.code not in confirmed:
            _rec(R, "syllabus_signal", f"{syl.code}: {sk.name} mentioned (unreviewed signal)", f"/gap/analysis/{ga.id}" if ga else f"/gap/course/{syl.id}",
                 {"level_signal": "practiced?" if info["mentions"] >= 2 else "introduced?", "mentions": info["mentions"],
                  "excerpt": (info.get("excerpts") or [""])[0]})
    from ..models import CourseSkill

    cat = sorted(c.code for c in db.scalars(select(Course).join(CourseSkill, CourseSkill.course_id == Course.id).where(
        Course.org_id == s["org_id"], CourseSkill.skill_id == sk.id, CourseSkill.weight >= 1.0)) if c.code not in confirmed)
    if cat:
        _rec(R, "catalog", f"{sk.name}: named in catalog descriptions", "/catalog", {"courses": ", ".join(cat[:15]) + (f" and {len(cat) - 15} more" if len(cat) > 15 else "")})
    from sqlalchemy import func

    n = db.scalar(select(func.count(func.distinct(SkillBadge.student_id))).where(SkillBadge.org_id == s["org_id"], SkillBadge.skill_id == sk.id,
                                                                                 SkillBadge.status == "active")) or 0
    _rec(R, "badges", f"{sk.name}: students with a faculty-verified badge", "/curriculum?tab=outcomes", {"students": n})


def _g_aacsb(db: Session, s: State, R: list[dict]) -> None:
    _g_where(db, s, R)
    sk = db.scalar(select(Skill).where(Skill.name == s["skill"]))
    if not sk:
        return
    for d in db.scalars(select(GapDecision).where(GapDecision.org_id == s["org_id"], GapDecision.skill_id == sk.id,
                                                  GapDecision.status.in_(("open", "drafted", "implemented")))):
        syl = db.get(Syllabus, d.syllabus_id)
        _rec(R, "decision", f"{syl.code}: {d.decision.replace('_', ' ')} ({d.status})", f"/gap/course/{syl.id}?tab=decisions",
             {"rationale": d.rationale, "decided": f"{d.decided_at.date()} by {d.reviewer_name or 'former faculty member'}",
              "evidence": f"{(d.evidence or {}).get('postings_requesting')} of {(d.evidence or {}).get('postings_in_sample')} sampled postings"})


def _g_undecided(db: Session, s: State, R: list[dict]) -> None:
    for syl in _syllabi(db, s, s.get("course"))[:30]:
        if not syl.analyses:
            continue
        ga = syl.analyses[0]
        decided = set(db.scalars(select(GapDecision.skill_id).where(GapDecision.syllabus_id == syl.id, GapDecision.status != "superseded")))
        for g in ga.result.get("gaps", []):
            if g["priority"] in ("critical", "high") and g["skill_id"] not in decided:
                _rec(R, "gap", f"{syl.code}: {g['name']} ({g['priority']})", f"/gap/analysis/{ga.id}",
                     {"status": g["status"], "share_of_postings": f"{round(g['demand'] * 100)}%", "postings": f"{g['job_count']} of {ga.job_count}"})
        if len(R) >= 15:
            return


def _g_proposals(db: Session, s: State, R: list[dict]) -> None:
    for p in db.scalars(select(CurriculumProposal).where(CurriculumProposal.org_id == s["org_id"], CurriculumProposal.status != "draft")
                        .order_by(CurriculumProposal.number.desc()).limit(10)):
        syl = db.get(Syllabus, p.syllabus_id)
        votes = [r for r in p.reviews if r.revision == p.revision]
        _rec(R, "proposal", f"Proposal #{p.number}: {p.title}", f"/curriculum/proposals/{p.id}",
             {"course": syl.code if syl else None, "status": p.status, "revision": p.revision, "effective_term": p.effective_term,
              "approvals": f"{sum(v.vote == 'approve' for v in votes)} of {p.required_approvals}",
              "changes_requested": sum(v.vote == "request_changes" for v in votes), "author": p.author_name})


TOOLS = {"score_change": _g_score_change, "unimplemented": _g_unimplemented, "overlap": _g_overlap, "aacsb_summary": _g_aacsb,
         "undecided_gaps": _g_undecided, "proposals": _g_proposals, "where_taught": _g_where}


def gather(s: State, db: Session) -> State:
    R: list[dict] = []
    TOOLS[s["intent"]](db, s, R)
    return {"records": R[:20], "steps": s["steps"] + [f"gather → {len(R[:20])} records"]}


# ── node: write ────────────────────────────────────────────────────────────────
class _Answer(BaseModel):
    answer: str = Field(description="Markdown answer. Cite records as [n]. Use only the records' facts.")


def _template(s: State) -> str:
    R, i = s["records"], s["intent"]
    if i == "score_change":
        c = R[0]["facts"]
        asked_down = any(k in s["question"].lower() for k in ("drop", "fell", "decline", "went down", "decrease"))
        asked_up = any(k in s["question"].lower() for k in ("rise", "rose", "went up", "increase"))
        parts = [f"**{c['course']}** went from {c['from']} to {c['to']}: **{c['total_change']:+} points** [1]."]
        if (asked_down and c["total_change"] > 0) or (asked_up and c["total_change"] < 0):
            parts.append(f"So between the latest two reports it actually {'rose' if c['total_change'] > 0 else 'fell'}.")
        parts.append(f"Course revision {c['course_revision']:+}, demand change {c['demand_change']:+}, method update {c['method_update']:+} [1].")
        main = max(("course revision", c["course_revision"]), ("demand change", c["demand_change"]), ("method update", c["method_update"]), key=lambda x: abs(x[1]))
        parts.append(f"Most of the change comes from the **{main[0]}**" + (" (the job sample changed: " + c["postings"] + " postings)." if main[0] == "demand change" else "."))
        if len(R) > 1:
            def desc(f):
                a, b = f["status"].split(" → ")
                if a == "None":
                    return f"entered the top skills as {b} ({f['share_of_postings'].split(' → ')[1]} of postings)"
                if b == "None":
                    return "dropped out of the top skills"
                return f"{a} → {b}" if a != b else f"share of postings {f['share_of_postings']}"
            parts.append("Skills that changed: " + "; ".join(f"{r['title'].split(': ', 1)[1]} {desc(r['facts'])} ({r['facts']['why']}) [{r['n']}]" for r in R[1:6]) + ".")
        return " ".join(parts)
    if i == "unimplemented":
        return f"**{len(R)} accepted change{'s' if len(R) != 1 else ''}** {'are' if len(R) != 1 else 'is'} not implemented yet:\n\n" + "\n".join(
            f"- {r['title']} — {r['facts']['status']}, decided {r['facts']['decided']}"
            + (f"; a later syllabus version mentions it (v{r['facts']['mention_signal_in_later_version']})" if r["facts"]["mention_signal_in_later_version"] else "")
            + f" [{r['n']}]" for r in R)
    if i == "overlap":
        return "Skills that faculty confirmed in more than one course:\n\n" + "\n".join(f"- **{r['title']}**: {r['facts']['courses']} [{r['n']}]" for r in R) + \
            "\n\nWhere two courses both practice a skill, consider a prerequisite link or shared materials so the second course can go deeper."
    if i in ("where_taught", "aacsb_summary"):
        lines = [f"## {'Assurance of learning: ' if i == 'aacsb_summary' else ''}{s['skill']}"] if i == "aacsb_summary" else []
        for r in R:
            f = r["facts"]
            if r["type"] == "faculty_levels":
                lines.append(f"- **Faculty-confirmed coverage:** {f['courses']} [{r['n']}]")
            elif r["type"] == "syllabus_signal":
                lines.append(f"- {r['title']}: {f['mentions']} mention(s), probably {f['level_signal'].rstrip('?')}, not yet reviewed by faculty [{r['n']}]")
            elif r["type"] == "catalog":
                lines.append(f"- Catalog descriptions name it in: {f['courses']} (unverified) [{r['n']}]")
            elif r["type"] == "badges":
                lines.append("- **Evidence of student achievement:** " + (f"{f['students']} student{'s hold' if f['students'] != 1 else ' holds'} a faculty-verified {s['skill']} badge" if f["students"]
                             else f"no student holds a faculty-verified {s['skill']} badge yet") + f" [{r['n']}]")
            elif r["type"] == "decision":
                lines.append(f"- **Curriculum action:** {r['title']}, {f['decided']}: {f['rationale']} [{r['n']}]")
        if i == "aacsb_summary":
            lines.append("\n*Draft for the assurance-of-learning report. Levels marked “faculty review” or “curriculum map” are faculty-confirmed; keyword signals are not.*")
        return "\n".join(lines)
    if i == "undecided_gaps":
        return f"**{len(R)} priority gaps** have no faculty decision yet:\n\n" + "\n".join(f"- {r['title']}: {r['facts']['share_of_postings']} of postings [{r['n']}]" for r in R)
    if i == "proposals":
        return "\n".join(f"- **{r['title']}** ({r['facts']['course']}): {r['facts']['status'].replace('_', ' ')}, {r['facts']['approvals']} approvals"
                         + (f", {r['facts']['changes_requested']} requesting changes" if r["facts"]["changes_requested"] else "") + f" [{r['n']}]" for r in R)
    return ""


def write(s: State, db: Session) -> State:
    import json

    r = ai.structured(
        system=("You answer questions for university faculty and deans using ONLY the numbered records provided. "
                "Cite every fact with its record number in square brackets, like [2]. Never add numbers, names or claims that are not in the records. "
                "If the records do not answer the question, say so. Be concise; use short markdown lists where helpful."),
        prompt=f"Question: {s['question']}\n\nRecords:\n" + json.dumps(s["records"], indent=1, default=str),
        schema=_Answer, effort="medium", max_tokens=8000)
    if r and r.answer.strip():
        return {"answer": r.answer, "engine": "claude", "steps": s["steps"] + ["write → Claude"]}
    return {"answer": _template(s), "steps": s["steps"] + ["write → built-in template"]}


# ── node: verify ───────────────────────────────────────────────────────────────
def verify(s: State, db: Session) -> State:
    R = s.get("records", [])
    valid = {r["n"] for r in R}
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", s.get("answer", ""))}
    answer = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid else "", s.get("answer", ""))
    used = sorted(cited & valid) or sorted(valid)
    dropped = len(cited - valid)
    return {"answer": answer.strip(), "citations": [{"n": r["n"], "title": r["title"], "link": r["link"], "type": r["type"]} for r in R if r["n"] in used],
            "steps": s["steps"] + [f"verify → {len(used)} sources" + (f", {dropped} unsupported citation(s) removed" if dropped else "")]}


def help_node(s: State, db: Session) -> State:
    return {"answer": "I answer from CometIQ's own records only. Try one of these:\n\n" + "\n".join(f"- {e}" for e in EXAMPLES)
            + "\n\nName a course code (e.g. BUAN 6356) or a skill (e.g. SQL) where the question is about one.",
            "records": [], "citations": [], "steps": s["steps"] + ["help"]}


def no_records(s: State, db: Session) -> State:
    what = {"score_change": "two versioned reports for that course", "unimplemented": "open accepted changes",
            "overlap": "skills confirmed in more than one course", "undecided_gaps": "undecided priority gaps",
            "proposals": "submitted proposals"}.get(s["intent"], "records")
    return {"answer": f"I couldn't find {what} you have access to, so I won't guess." + (f" (Course: {s['course']}.)" if s.get("course") else ""),
            "citations": [], "steps": s["steps"] + ["no records → stop"]}


# ── graph ──────────────────────────────────────────────────────────────────────
def build_graph(db: Session):
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(State)
    g.add_node("understand", lambda s: understand(s, db))
    g.add_node("help", lambda s: help_node(s, db))
    g.add_node("gather", lambda s: gather(s, db))
    g.add_node("no_records", lambda s: no_records(s, db))
    g.add_node("write", lambda s: write(s, db))
    g.add_node("verify", lambda s: verify(s, db))
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", lambda s: "help" if s["intent"] == "help" else "gather", {"help": "help", "gather": "gather"})
    g.add_conditional_edges("gather", lambda s: "write" if s["records"] else "no_records", {"write": "write", "no_records": "no_records"})
    g.add_edge("write", "verify")
    g.add_edge("verify", END)
    g.add_edge("help", END)
    g.add_edge("no_records", END)
    return g.compile()


def ask(db: Session, user: User, question: str) -> dict:
    out = build_graph(db).invoke({"question": question.strip(), "org_id": user.org_id, "user_id": user.id, "role": user.role, "steps": []})
    return {"question": question, "answer": out.get("answer", ""), "citations": out.get("citations", []), "intent": out.get("intent"),
            "course": out.get("course"), "skill": out.get("skill"), "engine": out.get("engine", "builtin"), "steps": out.get("steps", []),
            "examples": EXAMPLES}
