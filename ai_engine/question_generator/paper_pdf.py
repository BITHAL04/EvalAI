"""Printable question paper. Contains no answers or rubrics."""
from __future__ import annotations

import io
from dataclasses import dataclass
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class PaperData:
    institution: str
    title: str
    subject: str
    duration_minutes: int
    max_marks: float
    instructions: str
    questions: list[tuple[int, str, float]]


def render_paper(p: PaperData) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    head = ParagraphStyle("h", parent=styles["Title"], fontSize=16, spaceAfter=2, alignment=TA_CENTER)
    sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=12, alignment=TA_CENTER, spaceAfter=2)
    body = ParagraphStyle("b", parent=styles["Normal"], fontSize=11, leading=15)

    def footer(c, d):
        c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
        c.drawCentredString(A4[0] / 2, 1 * cm, f"Page {d.page}")

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            title=p.title, author=p.institution)
    s = [Paragraph(escape(p.institution), head), Paragraph(f"<b>{escape(p.title)}</b>", sub), Paragraph(escape(p.subject), sub), Spacer(1, 8)]
    meta = Table([[f"Duration: {p.duration_minutes} minutes", f"Maximum marks: {p.max_marks:g}"]], colWidths=[8.5 * cm] * 2)
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), .75, colors.black),
                              ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold")]))
    student = Table([["Student name: ____________________________", "Roll number: __________________"],
                     ["Date: ____________________", "Signature: ____________________"]], colWidths=[9.5 * cm, 7.5 * cm], rowHeights=[22, 22])
    s += [meta, Spacer(1, 8), student, Spacer(1, 10)]
    lines = [l.strip() for l in (p.instructions or "").splitlines() if l.strip()] or [
        "Answer all questions.", "Write the question number clearly before each answer.", "Number every page of your answer booklet."]
    s.append(Paragraph("<b>General instructions</b>", body))
    s += [Paragraph(f"{i}. {escape(l)}", body) for i, l in enumerate(lines, 1)]
    s.append(Spacer(1, 12))
    for n, text, marks in p.questions:
        row = Table([[Paragraph(f"<b>Q{n}.</b>", body), Paragraph(escape(text).replace("\n", "<br/>"), body), Paragraph(f"<b>[{marks:g}]</b>", body)]],
                    colWidths=[1.2 * cm, 14.3 * cm, 1.5 * cm])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        s.append(KeepTogether([row, Spacer(1, 8)]))
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
