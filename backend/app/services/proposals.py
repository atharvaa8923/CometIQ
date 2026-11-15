"""Curriculum proposals: syllabus changes reviewed like pull requests.

A proposal freezes the proposed syllabus text for each revision, shows it as a diff against the syllabus version it was
based on, collects line comments and reviews (approve / request changes) from faculty other than the author, and once
approved can be adopted as the course's next syllabus version. It also produces a course change request form.
"""
import difflib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (CurriculumProposal, ForgeDraft, GapAnalysis, GapDecision, JobSample, ProposalReview, Syllabus,
                      SyllabusVersion, User)
from . import forge as forgesvc
from . import versions as vs
from .decisions import DECISIONS

OPEN = ("draft", "in_review", "changes_requested", "approved")


def _now():
    return datetime.now(timezone.utc)


def proposed_from_current(base_text: str, content: dict) -> str:
    """The current syllabus with the draft's new items appended as a marked section, so the diff shows only additions."""
    new_out = [o for o in content.get("learning_outcomes", []) if o.get("is_new")]
    new_mod = [m for m in content.get("modules", []) if m.get("is_new")]
    added = set(content.get("gaps_addressed") or [])
    assess = [a for a in content.get("assessments", []) if set(a.get("skills", [])) & added]
    lines = [base_text.rstrip(), "", "PROPOSED CHANGES"]
    if new_out:
        lines += ["New learning outcomes:"] + [f"{o['id']}. {o['text']}" for o in new_out]
    if new_mod:
        lines += ["New or revised weekly modules:"] + [
            f"Week {m['week']}: {m['title']}" + (f" — {'; '.join(m.get('topics', []))}" if m.get("topics") else "") for m in new_mod]
    if assess:
        lines += ["Assessments that address the new skills:"] + [f"{a['name']} ({a['weight']}%): {a['description']}" for a in assess]
    return "\n".join(lines)


def full_draft_text(content: dict) -> str:
    return forgesvc.to_text(forgesvc.ForgeSyllabus(**content))


def diff_rows(left: str, right: str) -> list[dict]:
    """Side-by-side rows: equal / insert / delete / replace, with line numbers on each side (1-based, as in the text)."""
    a, b = left.splitlines(), right.splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            rows += [{"type": "equal", "l": i + 1, "left": a[i], "r": j + 1, "right": b[j]} for i, j in zip(range(i1, i2), range(j1, j2))]
        elif tag == "delete":
            rows += [{"type": "delete", "l": i + 1, "left": a[i], "r": None, "right": None} for i in range(i1, i2)]
        elif tag == "insert":
            rows += [{"type": "insert", "l": None, "left": None, "r": j + 1, "right": b[j]} for j in range(j1, j2)]
        else:
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                i, j = i1 + k, j1 + k
                rows.append({"type": "replace", "l": i + 1 if i < i2 else None, "left": a[i] if i < i2 else None,
                             "r": j + 1 if j < j2 else None, "right": b[j] if j < j2 else None})
    return rows


def _evidence(db: Session, syl: Syllabus, content: dict | None, decisions: list[GapDecision]) -> dict:
    ga = db.scalar(select(GapAnalysis).where(GapAnalysis.syllabus_id == syl.id).order_by(GapAnalysis.created_at.desc()).limit(1))
    added = {d.skill.name for d in decisions if d.decision == "add_here"}
    smp = db.get(JobSample, ga.sample_id) if ga and ga.sample_id else None
    return {
        "analysis_id": ga.id if ga else None,
        "current_score": ga.score if ga else None,
        "projected_score": forgesvc.projected_score(ga.result, added) if ga else None,
        "score_basis": "mention-based; projected = the accepted skills counted as covered",
        "sample": {"name": smp.name if smp else (ga.target if ga else None), "kind": smp.kind if smp else None,
                   **(vs.snapshot_summary(smp.snapshot) if smp and smp.snapshot else {})},
        "scoring_version": ga.scoring_version if ga else None,
        "decisions": [{"id": d.id, "skill": d.skill.name, "decision": d.decision, "label": DECISIONS[d.decision], "rationale": d.rationale,
                       "covered_in": d.covered_in or [], "revisit_term": d.revisit_term, "reviewer": d.reviewer_name,
                       "decided_at": d.decided_at.isoformat(), "postings_requesting": (d.evidence or {}).get("postings_requesting"),
                       "postings_in_sample": (d.evidence or {}).get("postings_in_sample"),
                       "syllabus_version": (d.evidence or {}).get("syllabus_version")} for d in decisions],
        "new_outcomes": [o for o in (content or {}).get("learning_outcomes", []) if o.get("is_new")],
    }


def create(db: Session, user: User, syl: Syllabus, title: str, summary: str, effective_term: str | None,
           draft_id: str | None, start_from: str = "current") -> CurriculumProposal:
    draft = db.get(ForgeDraft, draft_id) if draft_id else None
    if draft_id and (not draft or draft.syllabus_id != syl.id or draft.org_id != user.org_id):
        raise HTTPException(404, "Draft not found for this course")
    base = vs.ensure_version(db, syl, user_id=user.id)
    content = draft.content if draft else None
    if start_from == "draft" and content:
        text = full_draft_text(content)
    elif content:
        text = proposed_from_current(base.raw_text, content)
    else:
        text = base.raw_text
    decisions = list(db.scalars(select(GapDecision).where(GapDecision.syllabus_id == syl.id, GapDecision.status.in_(("open", "drafted", "implemented")))))
    number = (db.scalar(select(func.max(CurriculumProposal.number)).where(CurriculumProposal.org_id == user.org_id)) or 0) + 1
    p = CurriculumProposal(org_id=user.org_id, number=number, syllabus_id=syl.id, title=title.strip(), summary=summary.strip(),
                           author_id=user.id, author_name=user.full_name, base_version_id=base.id, forge_draft_id=draft.id if draft else None,
                           proposed_text=text, proposed_content=content, decision_ids=[d.id for d in decisions],
                           evidence=_evidence(db, syl, content, decisions), effective_term=(effective_term or "").strip() or None,
                           required_approvals=max(1, get_settings().CURRICULUM_APPROVALS))
    db.add(p)
    db.flush()
    return p


def current_votes(p: CurriculumProposal) -> dict[str, ProposalReview]:
    """Latest vote per reviewer on the current revision."""
    out: dict[str, ProposalReview] = {}
    for r in p.reviews:
        if r.revision == p.revision and r.reviewer_id:
            out[r.reviewer_id] = r
    return out


def tally(p: CurriculumProposal) -> dict:
    votes = current_votes(p).values()
    return {"approvals": sum(v.vote == "approve" for v in votes), "changes_requested": sum(v.vote == "request_changes" for v in votes),
            "required": p.required_approvals}


def update_status(p: CurriculumProposal) -> None:
    if p.status not in ("in_review", "changes_requested", "approved"):
        return
    t = tally(p)
    if t["changes_requested"]:
        p.status = "changes_requested"
    elif t["approvals"] >= p.required_approvals:
        if p.status != "approved":
            p.decided_at = _now()
        p.status = "approved"
    else:
        p.status = "in_review"


def out(db: Session, p: CurriculumProposal, full: bool = False) -> dict:
    syl = db.get(Syllabus, p.syllabus_id)
    base = db.get(SyllabusVersion, p.base_version_id) if p.base_version_id else None
    d = {"id": p.id, "number": p.number, "title": p.title, "summary": p.summary, "status": p.status, "revision": p.revision,
         "author": p.author_name or ("Former faculty member" if not p.author_id else None), "author_id": p.author_id,
         "syllabus": {"id": syl.id, "code": syl.code, "title": syl.title} if syl else None,
         "base_version": {"id": base.id, "version": base.version, "semester": base.semester} if base else None,
         "forge_draft_id": p.forge_draft_id, "effective_term": p.effective_term, "created_at": p.created_at,
         "submitted_at": p.submitted_at, "decided_at": p.decided_at, "adopted_version_id": p.adopted_version_id,
         "tally": tally(p), "open_comments": sum(not c.resolved for c in p.comments),
         "projected_score": (p.evidence or {}).get("projected_score"), "current_score": (p.evidence or {}).get("current_score")}
    if full:
        d |= {"evidence": p.evidence, "proposed_text": p.proposed_text,
              "diff": diff_rows(base.raw_text if base else "", p.proposed_text),
              "comments": [{"id": c.id, "author": c.author_name, "author_id": c.author_id, "anchor": c.anchor, "anchor_text": c.anchor_text,
                            "revision": c.revision, "body": c.body, "resolved": c.resolved, "created_at": c.created_at} for c in p.comments],
              "reviews": [{"id": r.id, "reviewer": r.reviewer_name, "reviewer_id": r.reviewer_id, "vote": r.vote, "body": r.body,
                           "revision": r.revision, "created_at": r.created_at, "current": r.revision == p.revision} for r in p.reviews]}
    return d


# ── Course change request form ─────────────────────────────────────────────────
def change_form(db: Session, p: CurriculumProposal) -> dict:
    syl = db.get(Syllabus, p.syllabus_id)
    base = db.get(SyllabusVersion, p.base_version_id) if p.base_version_id else None
    cv = vs.catalog_version(db, syl.org_id, syl.code)
    cat = cv.snapshot if cv else {}
    ev = p.evidence or {}
    decs = ev.get("decisions", [])
    content = p.proposed_content or {}
    smp = ev.get("sample") or {}
    votes = [r for r in p.reviews if r.revision == p.revision]
    return {
        "note": "Prepared by CometIQ from an approved curriculum proposal. This is a generic course change template: copy the "
                "fields into the university's curriculum system, where field names may differ.",
        "course": {"code": syl.code, "title": cat.get("title") or syl.title, "credits": cat.get("credits"),
                   "catalog_year": cv.catalog_year if cv else None, "programs": [x["name"] for x in cat.get("programs", [])]},
        "proposal": {"number": p.number, "revision": p.revision, "title": p.title, "status": p.status, "author": p.author_name,
                     "effective_term": p.effective_term, "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
                     "decided_at": p.decided_at.isoformat() if p.decided_at else None},
        "change_type": "Course content and learning outcomes. No change to course title, credit hours or prerequisites.",
        "summary": p.summary,
        "justification": [f"{d['skill']}: {d['label']}. {d['rationale']}"
                          + (f" (requested by {d['postings_requesting']} of {d['postings_in_sample']} sampled postings)" if d.get("postings_requesting") else "")
                          + (f" Covered in {', '.join(d['covered_in'])}." if d.get("covered_in") else "")
                          + (f" Revisit {d['revisit_term']}." if d.get("revisit_term") else "") for d in decs],
        "outcomes_current": forgesvc.existing_objectives(base.raw_text if base else "", limit=12),
        "outcomes_proposed": [f"{o['id']}. {o['text']}" + (" (new)" if o.get("is_new") else "") for o in content.get("learning_outcomes", [])],
        "assessments_proposed": [f"{a['name']} ({a['weight']}%): {a['description']}" for a in content.get("assessments", [])],
        "other_courses": [f"{d['skill']} is covered in {', '.join(d['covered_in'])}" for d in decs if d["decision"] == "covered_elsewhere"],
        "evidence": {"job_sample": smp.get("name"), "postings": smp.get("total"), "dates": f"{smp.get('date_from') or '?'} to {smp.get('date_to') or '?'}",
                     "current_score": ev.get("current_score"), "projected_score": ev.get("projected_score"), "score_basis": ev.get("score_basis"),
                     "base_version": f"v{base.version} ({base.semester or 'no term'})" if base else None},
        "approvals": [{"reviewer": r.reviewer_name, "vote": "Approved" if r.vote == "approve" else "Changes requested", "date": r.created_at.date().isoformat(),
                       "comment": r.body or ""} for r in votes],
        "required_approvals": p.required_approvals,
    }


def change_form_pdf(form: dict) -> bytes:
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import ListFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as x

    from .reports import GREEN, _styles

    ss, buf = _styles(), io.BytesIO()
    c, pr, ev = form["course"], form["proposal"], form["evidence"]
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch,
                            title=f"Course change request — {c['code']}")

    def bullets(items):
        return ListFlowable([Paragraph(x(i), ss["BodyText"]) for i in items], bulletType="bullet") if items else Paragraph("None", ss["BodyText"])

    rows = [["Course", f"{c['code']} {c['title']}"], ["Credit hours", str(c.get("credits") or "")], ["Catalog year", c.get("catalog_year") or ""],
            ["Programs", ", ".join(c.get("programs") or [])], ["Proposal", f"#{pr['number']} (revision {pr['revision']}): {pr['title']}"],
            ["Proposed by", pr.get("author") or ""], ["Effective term", pr.get("effective_term") or ""], ["Status", pr["status"]]]
    t = Table([[Paragraph(f"<b>{x(a)}</b>", ss["Small"]), Paragraph(x(b), ss["Small"])] for a, b in rows], colWidths=[1.5 * inch, 5.3 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GREEN), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el = [Paragraph("Course change request", ss["H"]), Paragraph(x(form["note"]), ss["Small"]), Spacer(1, 8), t,
          Paragraph("Type of change", ss["H2c"]), Paragraph(x(form["change_type"]), ss["BodyText"]),
          Paragraph("Summary of the change", ss["H2c"]), Paragraph(x(form["summary"] or ""), ss["BodyText"]),
          Paragraph("Justification", ss["H2c"]), bullets(form["justification"]),
          Paragraph("Current learning outcomes", ss["H2c"]), bullets(form["outcomes_current"]),
          Paragraph("Proposed learning outcomes", ss["H2c"]), bullets(form["outcomes_proposed"]),
          Paragraph("Proposed assessments", ss["H2c"]), bullets(form["assessments_proposed"]),
          Paragraph("Impact on other courses", ss["H2c"]), bullets(form["other_courses"]),
          Paragraph("Evidence", ss["H2c"]),
          Paragraph(x(f"Job sample: {ev.get('job_sample')} ({ev.get('postings')} postings, {ev.get('dates')}). Based on syllabus {ev.get('base_version')}. "
                      f"Coverage {ev.get('current_score')}% → projected {ev.get('projected_score')}% ({ev.get('score_basis')})."), ss["BodyText"]),
          Paragraph(f"Approvals ({form['required_approvals']} required)", ss["H2c"]),
          bullets([f"{a['reviewer']}: {a['vote']}, {a['date']}" + (f" — {a['comment']}" if a["comment"] else "") for a in form["approvals"]])]
    doc.build(el)
    return buf.getvalue()


def change_form_docx(form: dict) -> bytes:
    import io

    import docx

    c, pr, ev = form["course"], form["proposal"], form["evidence"]
    d = docx.Document()
    d.add_heading("Course change request", 0)
    d.add_paragraph().add_run(form["note"]).italic = True
    t = d.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for a, b in [("Course", f"{c['code']} {c['title']}"), ("Credit hours", str(c.get("credits") or "")), ("Catalog year", c.get("catalog_year") or ""),
                 ("Programs", ", ".join(c.get("programs") or [])), ("Proposal", f"#{pr['number']} (revision {pr['revision']}): {pr['title']}"),
                 ("Proposed by", pr.get("author") or ""), ("Effective term", pr.get("effective_term") or ""), ("Status", pr["status"])]:
        r = t.add_row().cells
        r[0].text, r[1].text = a, b
    for head, items in [("Type of change", [form["change_type"]]), ("Summary of the change", [form["summary"] or ""]),
                        ("Justification", form["justification"]), ("Current learning outcomes", form["outcomes_current"]),
                        ("Proposed learning outcomes", form["outcomes_proposed"]), ("Proposed assessments", form["assessments_proposed"]),
                        ("Impact on other courses", form["other_courses"] or ["None"]),
                        ("Evidence", [f"Job sample: {ev.get('job_sample')} ({ev.get('postings')} postings, {ev.get('dates')}). Based on syllabus {ev.get('base_version')}.",
                                      f"Coverage {ev.get('current_score')}% → projected {ev.get('projected_score')}% ({ev.get('score_basis')})."]),
                        (f"Approvals ({form['required_approvals']} required)",
                         [f"{a['reviewer']}: {a['vote']}, {a['date']}" + (f" — {a['comment']}" if a["comment"] else "") for a in form["approvals"]] or ["None yet"])]:
        d.add_heading(head, 1)
        for i in items:
            d.add_paragraph(i, style="List Bullet" if len(items) > 1 else None)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
