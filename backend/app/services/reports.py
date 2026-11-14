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
