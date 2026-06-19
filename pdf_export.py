"""
pdf_export.py — render a saved consultation case (dict) to a clean PDF.

Uses reportlab (pure Python, no system dependencies — installs fine on Windows).
Input is the same dict shape saved by app.save_case / results.json.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
)

ACCENT = colors.HexColor("#0F6E56")
MUTED = colors.HexColor("#666666")


def _styles():
    ss = getSampleStyleSheet()
    out = {
        "title": ParagraphStyle(
            "vsTitle", parent=ss["Title"], textColor=ACCENT, fontSize=20,
            spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "vsMeta", parent=ss["Normal"], textColor=MUTED, fontSize=9,
            spaceAfter=10,
        ),
        "h": ParagraphStyle(
            "vsH", parent=ss["Heading2"], textColor=ACCENT, fontSize=12,
            spaceBefore=12, spaceAfter=4,
        ),
        "lbl": ParagraphStyle(
            "vsLbl", parent=ss["Normal"], textColor=ACCENT, fontSize=9,
            spaceBefore=6, spaceAfter=1, leading=11,
        ),
        "body": ParagraphStyle(
            "vsBody", parent=ss["Normal"], fontSize=10.5, leading=15,
            alignment=TA_LEFT,
        ),
        "small": ParagraphStyle(
            "vsSmall", parent=ss["Normal"], fontSize=9, textColor=MUTED,
            leading=12,
        ),
    }
    return out


def _p(text, style):
    return Paragraph(escape(str(text or "")), style)


def build_pdf(d: dict, out_path: str) -> str:
    """Render case dict `d` to a PDF at out_path. Returns out_path."""
    st = _styles()
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="VetScribe Consultation Note",
    )
    story = []

    story.append(_p("VetScribe — Consultation Note", st["title"]))
    when = (d.get("created_utc") or "")[:16].replace("T", " ")
    meta = " · ".join(
        x for x in [d.get("patient", ""), f"Model: {d.get('model', '')}", when] if x
    )
    story.append(_p(meta, st["meta"]))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#9FE1CB")))

    # SOAP
    soap = d.get("soap") or {}
    story.append(_p("SOAP note", st["h"]))
    for key, label in [
        ("subjective", "Subjective"), ("objective", "Objective"),
        ("assessment", "Assessment"), ("plan", "Plan"),
    ]:
        story.append(_p(label.upper(), st["lbl"]))
        story.append(_p(soap.get(key, "Not documented in consultation."), st["body"]))
    doses = soap.get("drug_dose_mentions") or []
    if doses:
        story.append(_p("Dosing mentions flagged for review", st["lbl"]))
        story.append(ListFlowable(
            [ListItem(_p(x, st["body"])) for x in doses], bulletType="bullet",
        ))

    # Owner summary
    owner = d.get("owner") or {}
    if owner.get("summary"):
        story.append(_p("Owner summary", st["h"]))
        for para in str(owner.get("summary", "")).split("\n"):
            if para.strip():
                story.append(_p(para, st["body"]))
        if owner.get("follow_up"):
            story.append(_p("Follow-up", st["lbl"]))
            story.append(_p(owner.get("follow_up"), st["body"]))

    # Transcript
    turns = d.get("turns") or []
    if turns:
        story.append(_p("Transcript", st["h"]))
        for t in turns:
            spk = escape(str(t.get("speaker", "?")))
            txt = escape(str(t.get("text", "")))
            story.append(Paragraph(f"<b>{spk}:</b> {txt}", st["body"]))

    # Insights
    m = d.get("metrics") or {}
    story.append(_p("Insights", st["h"]))
    metric_line = "  ·  ".join([
        f"Duration: {m.get('duration', '—')}",
        f"Est. time saved: {m.get('time_saved', '—')}",
        f"Vet talk ratio: {m.get('vet_ratio', '—')}",
        f"Entities: {m.get('entity_count', '—')}",
    ])
    story.append(_p(metric_line, st["small"]))

    ents = d.get("entities") or []
    if ents:
        story.append(_p("Clinical entities", st["lbl"]))
        story.append(_p(
            ", ".join(f"{e.get('text', '')} ({e.get('type', '')})" for e in ents),
            st["small"],
        ))

    flags = d.get("flags") or []
    story.append(_p("Research flags (human–AI gap)", st["lbl"]))
    if flags:
        for f in flags:
            story.append(Paragraph(
                f"<b>{escape(str(f.get('item', '')))}</b> — "
                f"{escape(str(f.get('why', '')))} "
                f"(evidence: “{escape(str(f.get('evidence', '')))}”)",
                st["small"],
            ))
    else:
        story.append(_p("None raised.", st["small"]))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#FAC775")))
    story.append(_p(
        "AI-generated draft · a licensed clinician must verify before signing. "
        "Research prototype — not for clinical use.", st["small"],
    ))

    doc.build(story)
    return out_path
