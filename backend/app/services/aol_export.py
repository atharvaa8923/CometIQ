"""The AACSB assurance-of-learning report as Word and PDF documents."""
import io
from datetime import date

from docx import Document
from docx.shared import Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .reports import GREEN, _styles

STATUS = {"met": "Met target", "below_with_action": "Below target, action recorded", "below": "Below target, no action yet",
          "not_assessed": "Not yet assessed", "gap": "Not practiced in any course"}


def _coverage_line(c: dict) -> str:
    parts = [f"{label}: {', '.join(c[k]) or 'none'}" for k, label in (("introduced_in", "Introduced"), ("practiced_in", "Practiced"),
                                                                        ("mastered_in", "Mastered"))]
    return "; ".join(parts)


def _intro(r: dict) -> list[str]:
    s = r["summary"]
    return [f"Program: {r['program']['name']}" + (f" (catalog {r['program']['catalog_year']})" if r["program"].get("catalog_year") else ""),
            f"Prepared {date.today():%B %d, %Y} with CometIQ from the program's curriculum map, Canvas assignments, faculty-entered "
            f"assessment results, faculty decisions and curriculum proposals.",
            f"{s['goals']} competency goals: {s['met']} met the target, {s['below_with_action']} below target with an action recorded, "
            f"{s['below']} below target without an action, {s['not_assessed']} not yet assessed, {s['gap']} not practiced in any course. "
            f"Terms assessed: {', '.join(s['terms_assessed']) or 'none yet'}. Direct measures available from graded work: {s['direct_measures']}."
            + (f" Industry alignment (share of employer demand the program covers): {s['industry_coverage']:.0f}%." if s.get("industry_coverage") is not None else "")]


def docx(r: dict) -> bytes:
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    h = d.add_heading("Assurance of Learning Report", 0)
    h.runs[0].font.color.rgb = RGBColor(0x0E, 0x42, 0x31)
    for p in _intro(r):
        d.add_paragraph(p)
    for g in r["goals"]:
        d.add_heading(f"{g['code']}: {g['title']}", 1)
        if g.get("description"):
            d.add_paragraph(g["description"])
        d.add_paragraph(f"Status: {STATUS.get(g['status'], g['status'])}. {g['status_text']}. Target: {g['target_pct']}% of students meet or exceed expectations.")
        d.add_paragraph("Skills: " + ", ".join(s["name"] for s in g["skills"]))
        for w in g.get("warnings", []):
            d.add_paragraph(f"Note: {w}.")
        d.add_heading("Where it is taught", 2)
        d.add_paragraph(_coverage_line(g["coverage"]))
        d.add_heading("Direct measures available (graded work)", 2)
        ms = [(sk["skill"], m) for sk in g["skills_detail"] for m in sk["measures"]]
        if ms:
            t = d.add_table(rows=1, cols=4)
            t.style = "Light Grid Accent 1"
            for i, x in enumerate(("Course", "Assignment", "Skill", "Rubric criteria")):
                t.rows[0].cells[i].text = x
            for skill, m in ms:
                row = t.add_row().cells
                row[0].text, row[1].text, row[2].text = m["course"], f"{m['assignment']} ({m['points'] or 0:g} pts)", skill
                row[3].text = "; ".join(m["rubric_criteria"]) or "—"
        else:
            d.add_paragraph("No graded assignments on record for these skills. Import the courses from Canvas to list them.")
        d.add_heading("Assessment results", 2)
        if g["results"]:
            t = d.add_table(rows=1, cols=6)
            t.style = "Light Grid Accent 1"
            for i, x in enumerate(("Term", "Course", "Measure", "Assessed", "Met", "Target")):
                t.rows[0].cells[i].text = x
            for res in g["results"]:
                row = t.add_row().cells
                row[0].text, row[1].text = res["term"], res["course_code"] or "—"
                row[2].text = f"{res['measure']} ({res['measure_type']})"
                row[3].text, row[4].text = str(res["students_assessed"]), f"{res['met_pct']:.0f}%" if res["met_pct"] is not None else "—"
                row[5].text = f"{res['target_pct']}%"
        else:
            d.add_paragraph("No results entered yet.")
        d.add_heading("Closing the loop", 2)
        if g["closing_the_loop"]:
            for item in g["closing_the_loop"]:
                d.add_paragraph(_loop_text(item), style="List Bullet")
        else:
            d.add_paragraph("No actions recorded yet.")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _loop_text(i: dict) -> str:
    if i["kind"] == "decision":
        return f"{i['course']}: faculty decision on {i['skill']} ({i['decision'].replace('_', ' ')}, {i['status']}). {i.get('rationale') or ''}".strip()
    if i["kind"] == "proposal":
        return f"{i['course']}: curriculum proposal {i['title']} ({i['status']}" + (f", effective {i['effective_term']}" if i.get("effective_term") else "") + ")"
    return f"{i.get('course') or ''} {i['term']}: {i['action']}".strip()


def pdf(r: dict) -> bytes:
    ss, buf = _styles(), io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.6 * inch,
                            title=f"Assurance of Learning: {r['program']['name']}")
    el = [Paragraph("Assurance of Learning Report", ss["H"])] + [Paragraph(p, ss["BodyText"]) for p in _intro(r)] + [Spacer(1, 6)]
    grid = [("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    summary = [["Goal", "Status", "Taught (P/M)", "Results"]] + [
        [Paragraph(f"<b>{g['code']}</b> {g['title']}", ss["Small"]), Paragraph(STATUS.get(g["status"], g["status"]), ss["Small"]),
         Paragraph(", ".join(g["coverage"]["practiced_in"] + g["coverage"]["mastered_in"]) or "—", ss["Small"]), str(len(g["results"]))]
        for g in r["goals"]]
    t = Table(summary, colWidths=[2.6 * inch, 1.6 * inch, 1.9 * inch, 0.8 * inch], repeatRows=1)
    t.setStyle(TableStyle(grid))
    el += [t]
    for g in r["goals"]:
        block = [Paragraph(f"{g['code']}: {g['title']}", ss["H2c"]),
                 Paragraph(f"<b>{STATUS.get(g['status'], g['status'])}</b>. {g['status_text']}. Target {g['target_pct']}%. "
                           f"Skills: {', '.join(s['name'] for s in g['skills'])}.", ss["BodyText"]),
                 Paragraph(f"<b>Where it is taught.</b> {_coverage_line(g['coverage'])}"
                           + "".join(f" <i>Note: {w}.</i>" for w in g.get("warnings", [])), ss["Small"])]
        ms = [(sk["skill"], m) for sk in g["skills_detail"] for m in sk["measures"]]
        block.append(Paragraph("<b>Direct measures (graded work).</b> " + ("; ".join(
            f"{m['course']} {m['assignment']} ({skill}{': ' + ', '.join(m['rubric_criteria']) if m['rubric_criteria'] else ''})" for skill, m in ms[:12])
            or "None on record."), ss["Small"]))
        if g["results"]:
            rows = [["Term", "Course", "Measure", "n", "Met", "Target"]] + [
                [x["term"], x["course_code"] or "—", Paragraph(f"{x['measure']} ({x['measure_type']})", ss["Small"]), str(x["students_assessed"]),
                 f"{x['met_pct']:.0f}%" if x["met_pct"] is not None else "—", f"{x['target_pct']}%"] for x in g["results"]]
            rt = Table(rows, colWidths=[0.9 * inch, 0.9 * inch, 3.0 * inch, 0.5 * inch, 0.6 * inch, 0.6 * inch], repeatRows=1)
            style = list(grid) + [("BACKGROUND", (4, i), (4, i), colors.HexColor("#d1ecdf" if x["met_target"] else "#fee2e2"))
                                  for i, x in enumerate(g["results"], 1)]
            rt.setStyle(TableStyle(style))
            block += [Spacer(1, 3), rt]
        else:
            block.append(Paragraph("<b>Assessment results.</b> None entered yet.", ss["Small"]))
        block.append(Paragraph("<b>Closing the loop.</b> " + (" ".join(f"• {_loop_text(i)}" for i in g["closing_the_loop"]) or "No actions recorded yet."), ss["Small"]))
        el.append(KeepTogether(block[:3]))
        el += block[3:]
    doc.build(el)
    return buf.getvalue()
