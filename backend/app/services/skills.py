"""Skill extraction: taxonomy matching (built-in) + optional Claude enrichment."""
import re
from collections import defaultdict
from functools import lru_cache

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.taxonomy import SKILLS
from ..models import Skill
from . import ai


@lru_cache
def _matchers() -> list[tuple[str, list[re.Pattern]]]:
    out = []
    for name, _cat, aliases, _em in SKILLS:
        pats = []
        # The skill name is itself an alias unless it is a 1–2 letter token (e.g. "R") or the skill uses a regex alias.
        all_aliases = set(aliases) | ({name.lower()} if len(name) > 2 and not any(a.startswith("re:") for a in aliases) else set())
        for a in all_aliases:
            if a.startswith("re:"):
                pats.append(re.compile(rf"(?<![\w]){a[3:]}(?![\w])", re.I))
            elif a.startswith("="):
                pats.append(re.compile(rf"(?<![\w/+#-]){re.escape(a[1:])}(?![\w+#-])"))
            else:
                pats.append(re.compile(rf"(?<![\w]){re.escape(a.lower())}(?![\w])", re.I))
        out.append((name, pats))
    return out


def _snippet(text: str, start: int, end: int, pad: int = 70) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s else "") + " ".join(text[s:e].split()) + ("…" if e < len(text) else "")


def _line(text: str, start: int, end: int, limit: int = 240) -> str:
    """The source line containing a match (trimmed around it), e.g. 'Week 3: Data wrangling with dplyr …'."""
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le == -1 else le
    line = " ".join(text[ls:le].split())
    if len(line) <= limit:
        return line
    rel = start - ls
    s = max(0, rel - limit // 2)
    return ("…" if s else "") + line[s:s + limit].strip() + "…"


def extract_builtin(text: str, max_excerpts: int = 3) -> dict[str, dict]:
    """{skill: {"mentions": int, "evidence": first excerpt, "excerpts": [up to 3 distinct source lines]}}."""
    found: dict[str, dict] = {}
    if not text:
        return found
    for name, pats in _matchers():
        hits = sorted(((m.start(), m.end()) for p in pats for m in p.finditer(text)))
        if not hits:
            continue
        excerpts: list[str] = []
        for s, e in hits:
            ln = _line(text, s, e)
            if ln and ln not in excerpts:
                excerpts.append(ln)
            if len(excerpts) >= max_excerpts:
                break
        found[name] = {"mentions": len(hits), "evidence": excerpts[0] if excerpts else _snippet(text, *hits[0]), "excerpts": excerpts}
    return found


class _AISkill(BaseModel):
    skill: str
    evidence: str
    importance: str  # required | preferred


class _AISkills(BaseModel):
    skills: list[_AISkill]


def extract(text: str, kind: str = "document") -> tuple[dict[str, dict], str]:
    """Hybrid extraction. Returns (skills, engine). Claude can only choose skills from the
    taxonomy, so results stay comparable across syllabi, jobs and resumes."""
    found = extract_builtin(text)
    if not ai.enabled() or len(text.strip()) < 40:
        return found, "builtin"
    names = [s[0] for s in SKILLS]
    res = ai.structured(
        system=(
            "You map documents onto a fixed skill taxonomy for a university/workforce analytics platform. "
            "Only return skills from the provided list, spelled exactly as listed. Include a skill only when the "
            "document clearly teaches, requires or demonstrates it, including when it is described without the exact keyword. "
            "evidence: a short quote or paraphrase from the document. importance: 'required' or 'preferred' "
            "(for syllabi and resumes always 'required')."
        ),
        prompt=f"Skill taxonomy:\n{', '.join(names)}\n\nDocument type: {kind}\n\n<document>\n{text[:60000]}\n</document>",
        schema=_AISkills,
        effort="low",
        max_tokens=8000,
    )
    if res is None:
        return found, "builtin"
    lookup = {n.lower(): n for n in names}
    for s in res.skills:
        n = lookup.get(s.skill.strip().lower())
        if not n:
            continue
        if n in found:
            found[n]["mentions"] += 1
        else:
            found[n] = {"mentions": 1, "evidence": s.evidence[:300], "excerpts": [f"(AI) {s.evidence[:240]}"], "importance": s.importance}
    return found, "claude"


def skill_ids(db: Session, names) -> dict[str, int]:
    names = list(names)
    if not names:
        return {}
    rows = db.execute(select(Skill.name, Skill.id).where(Skill.name.in_(names))).all()
    return {n: i for n, i in rows}


def importance_from_context(text: str, evidence: str) -> str:
    """Heuristic for job postings: mentions in a 'preferred / nice to have' context are preferred."""
    e = (evidence or "").lower()
    return "preferred" if any(k in e for k in ("preferred", "nice to have", "a plus", "bonus", "desired")) else "required"


def category_counts(skill_names) -> dict[str, int]:
    cat = {s[0]: s[1] for s in SKILLS}
    out: dict[str, int] = defaultdict(int)
    for n in skill_names:
        out[cat.get(n, "Other")] += 1
    return dict(out)
