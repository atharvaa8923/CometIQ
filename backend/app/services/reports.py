"""PDF / Excel exports for CometGap analyses."""
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN, ORANGE = colors.HexColor("#0e4231"), colors.HexColor("#e87500")
STATUS_COLOR = {"covered": colors.HexColor("#d1ecdf"), "partial": colors.HexColor("#fef3c7"), "missing": colors.HexColor("#fee2e2")}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H", parent=ss["Heading1"], textColor=GREEN, fontSize=18))
    ss.add(ParagraphStyle("H2c", parent=ss["Heading2"], textColor=GREEN, fontSize=13, spaceBefore=10))
    ss.add(ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8.5, leading=11))
    return ss


def gap_pdf(syl, ga) -> bytes:
    r, ss, buf = ga.result, _styles(), io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch,
                            title=f"CometGap report — {syl.title}")
    el = [Paragraph("COMET<font color='#e87500'>IQ</font> · CometGap Report", ss["H"]),
          Paragraph(f"<b>{syl.code or ''} {syl.title}</b> · {syl.semester or ''}", ss["BodyText"]),
          Paragraph(f"Target market: <b>{r['target']}</b> ({r['job_count']} postings) · Generated {ga.created_at:%Y-%m-%d} · Engine: {ga.engine}", ss["Small"]),
          Spacer(1, 8),
          Paragraph(f"<font size=22 color='#17684a'><b>{ga.score:.0f}%</b></font>&nbsp;&nbsp;industry coverage score — "
                    f"{r['counts']['covered']} covered · {r['counts']['partial']} partial · {r['counts']['missing']} missing", ss["BodyText"]),
          Spacer(1, 6), Paragraph(r["summary"], ss["BodyText"]), Paragraph("Recommendations", ss["H2c"])]
    for i, rec in enumerate(r["recommendations"], 1):
        el.append(Paragraph(f"<b>{i}. {rec['title']}</b> — {rec['detail']}", ss["BodyText"]))
        el.append(Spacer(1, 3))
    el.append(Paragraph("Skill coverage (top market skills)", ss["H2c"]))
    data = [["Skill", "Category", "Demand", "Priority", "Status"]]
    for s in r["skills"]:
        data.append([Paragraph(s["name"], ss["Small"]), Paragraph(s["category"], ss["Small"]), f"{s['demand']*100:.0f}%", s["priority"], s["status"]])
    t = Table(data, colWidths=[2.1 * inch, 1.9 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch], repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for i, s in enumerate(r["skills"], 1):
        style.append(("BACKGROUND", (4, i), (4, i), STATUS_COLOR[s["status"]]))
    t.setStyle(TableStyle(style))
    el.append(t)
    if r.get("emerging"):
        el.append(Paragraph("Emerging technologies", ss["H2c"]))
        el.append(Paragraph(", ".join(f"{e['name']} ({e['status']})" for e in r["emerging"]), ss["BodyText"]))
    doc.build(el)
    return buf.getvalue()


def gap_xlsx(syl, ga) -> bytes:
    r, wb = ga.result, Workbook()
    ws = wb.active
    ws.title = "Coverage"
    ws.append([f"CometGap — {syl.code or ''} {syl.title}", "", f"Target: {r['target']}", f"Score: {ga.score}%"])
    ws.append([])
    ws.append(["Skill", "Category", "Demand %", "Postings", "Priority", "Status", "Mentions", "Evidence", "Also taught in"])
    for c in ws[3]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0E4231")
    gaps = {g["name"]: g for g in r["gaps"]}
    fills = {"covered": "D1ECDF", "partial": "FEF3C7", "missing": "FEE2E2"}
    for s in r["skills"]:
        ws.append([s["name"], s["category"], round(s["demand"] * 100, 1), s["job_count"], s["priority"], s["status"],
                   s["mentions"], s.get("evidence") or "", ", ".join(gaps.get(s["name"], {}).get("taught_in", []))])
        ws.cell(ws.max_row, 6).fill = PatternFill("solid", fgColor=fills[s["status"]])
    for col, w in zip("ABCDEFGHI", (30, 26, 10, 10, 10, 10, 10, 60, 24)):
        ws.column_dimensions[col].width = w
    rec = wb.create_sheet("Recommendations")
    rec.append(["#", "Recommendation", "Detail", "Skills"])
    for i, x in enumerate(r["recommendations"], 1):
        rec.append([i, x["title"], x["detail"], ", ".join(x["skills"])])
    rec.column_dimensions["B"].width, rec.column_dimensions["C"].width = 34, 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── CometForge exports ─────────────────────────────────────────────────────────
def forge_docx(draft) -> bytes:
    import docx
    from docx.shared import Pt, RGBColor

    c = draft.content
    d = docx.Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    h = d.add_heading(f"{c.get('course_code', '')} {c['course_title']}".strip(), 0)
    h.runs[0].font.color.rgb = RGBColor(0x0E, 0x42, 0x31)
    d.add_paragraph(f"Syllabus draft v{draft.version} · generated with CometForge · {c.get('framework', '')} aligned")
    d.add_heading("Course description", 1)
    d.add_paragraph(c["description"])
    d.add_heading("Learning outcomes", 1)
    for o in c["learning_outcomes"]:
        p = d.add_paragraph(style="List Number")
        p.add_run(f"{o['id']} ").bold = True
        p.add_run(o["text"] + (" (new)" if o.get("is_new") else ""))
    d.add_heading("Course schedule", 1)
    t = d.add_table(rows=1, cols=4)
    t.style = "Light Grid Accent 1"
    for cell, txt in zip(t.rows[0].cells, ("Week", "Module", "Topics & activities", "Outcomes")):
        cell.text = txt
    for m in c["modules"]:
        r = t.add_row().cells
        r[0].text = str(m["week"])
        r[1].text = m["title"] + (" ★ new" if m.get("is_new") else "")
        r[2].text = "; ".join(m.get("topics", []) + m.get("activities", []))
        r[3].text = ", ".join(m.get("outcomes", []))
    d.add_heading("Assessment", 1)
    t = d.add_table(rows=1, cols=3)
    t.style = "Light Grid Accent 1"
    for cell, txt in zip(t.rows[0].cells, ("Component", "Weight", "Description")):
        cell.text = txt
    for a in c["assessments"]:
        r = t.add_row().cells
        r[0].text, r[1].text, r[2].text = a["name"], f"{a['weight']}%", a["description"]
    pr = c["project"]
    d.add_heading(f"Team project: {pr['title']}", 1)
    d.add_paragraph(pr["description"])
    for x in pr.get("deliverables", []):
        d.add_paragraph(x, style="List Bullet")
    if c.get("accreditation"):
        d.add_heading(f"Accreditation alignment ({c.get('framework', '')})", 1)
        for a in c["accreditation"]:
            d.add_paragraph(f"{a['standard']}: {', '.join(a['outcomes'])}", style="List Bullet")
    if c.get("program_goals"):
        d.add_heading("Program goals", 1)
        for g in c["program_goals"]:
            d.add_paragraph(f"{g['goal']}: {', '.join(g['outcomes']) or '—'}", style="List Bullet")
    if c.get("change_log"):
        d.add_heading("What changed and why", 1)
        for x in c["change_log"]:
            d.add_paragraph(x, style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def forge_pdf(draft) -> bytes:
    c, ss, buf = draft.content, _styles(), io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch,
                            title=f"{c['course_title']} syllabus")
    el = [Paragraph(f"{c.get('course_code', '')} {c['course_title']}", ss["H"]),
          Paragraph(f"Syllabus draft v{draft.version} · CometForge · {c.get('framework', '')} aligned", ss["Small"]),
          Paragraph("Course description", ss["H2c"]), Paragraph(c["description"], ss["BodyText"]),
          Paragraph("Learning outcomes", ss["H2c"])]
    el += [Paragraph(f"<b>{o['id']}</b> {o['text']}{' <font color=#e87500>(new)</font>' if o.get('is_new') else ''}", ss["BodyText"])
           for o in c["learning_outcomes"]]
    el.append(Paragraph("Course schedule", ss["H2c"]))
    data = [["Wk", "Module", "Topics & activities", "LOs"]]
    for m in c["modules"]:
        data.append([str(m["week"]), Paragraph(("<b>★</b> " if m.get("is_new") else "") + m["title"], ss["Small"]),
                     Paragraph("; ".join(m.get("topics", []) + m.get("activities", [])), ss["Small"]), Paragraph(", ".join(m.get("outcomes", [])), ss["Small"])])
    t = Table(data, colWidths=[0.4 * inch, 1.9 * inch, 3.6 * inch, 0.9 * inch], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(t)
    el.append(Paragraph("Assessment", ss["H2c"]))
    el += [Paragraph(f"<b>{a['name']}</b> — {a['weight']}%: {a['description']}", ss["BodyText"]) for a in c["assessments"]]
    pr = c["project"]
    el += [Paragraph(f"Team project: {pr['title']}", ss["H2c"]), Paragraph(pr["description"], ss["BodyText"])]
    el += [Paragraph(f"• {x}", ss["BodyText"]) for x in pr.get("deliverables", [])]
    if c.get("accreditation"):
        el.append(Paragraph(f"Accreditation alignment ({c.get('framework', '')})", ss["H2c"]))
        el += [Paragraph(f"<b>{a['standard']}</b>: {', '.join(a['outcomes'])}", ss["BodyText"]) for a in c["accreditation"]]
    doc.build(el)
    return buf.getvalue()


# ── CometPath degree plan PDF ──────────────────────────────────────────────────
def plan_pdf(d: dict) -> bytes:
    """d: student, program, concentration, career_goal, progress, completed, terms, readiness, review."""
    ss, buf = _styles(), io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch,
                            title=f"Degree plan — {d['student']}")
    p = d["progress"]
    el = [Paragraph("COMET<font color='#e87500'>IQ</font> · Degree &amp; Career Plan", ss["H"]),
          Paragraph(f"<b>{d['student']}</b> · {d['program'] or 'Program not set'}{' · ' + d['concentration'] if d['concentration'] else ''}", ss["BodyText"]),
          Paragraph(f"Career goal: <b>{d['career_goal'] or 'not set'}</b> · Generated {d['generated']}", ss["Small"]), Spacer(1, 6)]
    rv = d.get("review")
    if rv:
        color = {"approved": "#17684a", "changes_requested": "#c45f00", "submitted": "#1f4e79"}.get(rv["status"], "#334155")
        label = {"approved": "APPROVED by advisor", "changes_requested": "CHANGES REQUESTED by advisor", "submitted": "SUBMITTED — awaiting advisor review"}[rv["status"]]
        el.append(Paragraph(f"<font color='{color}'><b>{label}</b></font>"
                            + (f" — {rv['advisor']} ({rv['reviewed_at']})" if rv.get("advisor") else "")
                            + (f"<br/><i>{rv['advisor_note']}</i>" if rv.get("advisor_note") else "")
                            + (" <font color='#c45f00'>· Plan changed since approval</font>" if rv.get("changed_since") else ""), ss["BodyText"]))
    el.append(Paragraph("Progress", ss["H2c"]))
    el.append(Paragraph(f"Completed {p['sch']['completed']} of {p['total_sch']} SCH · enrolled {p['sch']['enrolled']} · planned {p['sch']['planned']} · "
                        f"core requirements {p['core']['done']}/{p['core']['total']} done", ss["BodyText"]))
    if d["completed"]:
        el.append(Paragraph("Completed / in progress: " + ", ".join(f"{c['code']} ({c['status']}{', ' + c['grade'] if c.get('grade') else ''})" for c in d["completed"]), ss["Small"]))
    el.append(Paragraph("Semester plan", ss["H2c"]))
    if not d["terms"]:
        el.append(Paragraph("No saved plan yet.", ss["BodyText"]))
    for t in d["terms"]:
        data = [[Paragraph(f"<b>{t['term']}</b> · {t['credits']} SCH", ss["Small"]), "", ""]]
        data += [[c["code"], Paragraph(c["title"], ss["Small"]), f"{c['credits']} SCH"] for c in t["courses"]]
        tb = Table(data, colWidths=[1.0 * inch, 4.9 * inch, 0.8 * inch])
        tb.setStyle(TableStyle([("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecf7f2")),
                                ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el += [tb, Spacer(1, 6)]
    r = d.get("readiness") or {}
    if r.get("goal"):
        el.append(Paragraph(f"Career readiness — {r['goal']}", ss["H2c"]))
        el.append(Paragraph(f"Today {round(r['now'])}% → with this plan {round(r['with_plan'])}% of the top in-demand skills "
                            f"(from {r['job_count']} current postings).", ss["BodyText"]))
        gaps = [s["skill"] for s in r["skills"] if s["status"] == "gap"]
        if gaps:
            el.append(Paragraph("Remaining skill gaps: " + ", ".join(gaps), ss["Small"]))
    el += [Spacer(1, 10), Paragraph("This plan is advisory. Confirm requirements with your academic advisor and the official catalog.", ss["Small"])]
    doc.build(el)
    return buf.getvalue()
