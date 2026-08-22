"""Final Exam Report — a real PDF built from this session's actual event
log and structured feedback labels (backend/db.py), not a static template
or a training-loss-style summary. Pulls fresh data at export time.

2026-08-23 rewrite: the old version correlated each alert's resolution via
a fuzzy free-text search over "feedback" events ("best-effort... approximate
join," per its own docstring). db.py's exam_report_data now does the exact
same real (seat_id, sim_time-within-3s) match against the FeedbackLabel
table the Evidence Vault and dispute-resolution pull-up already use — one
real source of truth for "what did a human decide about this alert,"
not three independently-drifting heuristics. Also adds a per-seat summary
and an explicit methodology section, so the report itself carries the
same "here's why this is trustworthy" standard every live alert already
does, not just a table of numbers.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import db

RESOLUTION_LABELS = {
    "confirmed": "Confirmed issue",
    "false_alarm": "False alarm",
    "no_action": "No action taken",
}


def generate_session_report_pdf(session_id: Optional[int], seat_ids: Optional[list[str]] = None) -> bytes:
    analytics = db.analytics_summary(session_id, seat_ids)
    report = db.exam_report_data(session_id, seat_ids)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.6 * inch, rightMargin=0.6 * inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("KTitle", parent=styles["Title"], fontSize=18, spaceAfter=4)
    meta_style = ParagraphStyle("KMeta", parent=styles["Normal"], textColor=colors.grey, fontSize=9)
    h2 = ParagraphStyle("KH2", parent=styles["Heading2"], spaceBefore=16, spaceAfter=6)
    body = ParagraphStyle("KBody", parent=styles["Normal"], fontSize=9, leading=12)

    scope_label = ", ".join(sorted(seat_ids)) if seat_ids else "all monitored seats"
    story = [
        Paragraph("KINESIS AI — Final Exam Report", title_style),
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · scoped to {scope_label}",
            meta_style,
        ),
        Spacer(1, 14),
        Paragraph("Summary", h2),
    ]

    summary_rows = [
        ["Total alerts", str(analytics["total_alerts"])],
        ["Seats with alert activity", str(len(analytics["alerts_per_seat"]))],
        ["Average risk score (all telemetry)", f"{analytics['avg_risk']:.3f}"],
        [
            "Average confidence, alerted detections",
            f"{report['avg_alert_confidence']:.2f}" if report["avg_alert_confidence"] is not None else "—",
        ],
        ["False alarms dismissed (baseline widened)", str(analytics["false_positives_dismissed"])],
        ["Structured training labels collected", str(report["total_labels"])],
    ]
    summary_table = Table(summary_rows, colWidths=[3.5 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
            ]
        )
    )
    story.append(summary_table)

    # Per-seat summary — the "how did each student's session actually go"
    # view a report needs that a flat alert list doesn't give you: a seat
    # with zero rows below never had an alert at all, which is itself the
    # expected, calm outcome for the overwhelming majority of real seats.
    story.append(Paragraph("Per-Seat Summary", h2))
    if not report["per_seat"]:
        story.append(Paragraph("No seat generated any alert this session — a fully calm session for the seats in scope.", body))
    else:
        header = ["Seat", "Alerts", "Confirmed", "False alarm", "No action", "Unresolved"]
        rows = [header] + [
            [
                s["seat_id"].upper(),
                str(s["alert_count"]),
                str(s["confirmed"]),
                str(s["false_alarm"]),
                str(s["no_action"]),
                str(s["unresolved"]),
            ]
            for s in report["per_seat"]
        ]
        seat_table = Table(rows, colWidths=[1.3 * inch] * 6, repeatRows=1)
        seat_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(seat_table)

    story.append(Paragraph("Alert Log", h2))
    if not report["alerts"]:
        story.append(Paragraph("No alerts recorded for this session.", body))
    else:
        header = ["Time (s)", "Seat", "Explanation", "Resolution", "Evidence"]
        rows = [header]
        for a in report["alerts"]:
            resolution = RESOLUTION_LABELS.get(a["resolution"], "Unresolved") if a["resolution"] else "Unresolved"
            evidence = "Yes — face-blurred clip" if a.get("evidence_url") else "—"
            rows.append(
                [
                    f"{a['sim_time']:.1f}",
                    a["seat_id"].upper(),
                    Paragraph(a.get("explanation") or "", body),
                    Paragraph(resolution, body),
                    evidence,
                ]
            )
        alert_table = Table(rows, colWidths=[0.6 * inch, 0.6 * inch, 2.9 * inch, 1.7 * inch, 1.1 * inch], repeatRows=1)
        alert_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(alert_table)

    story.append(Paragraph("Dispatch & Acknowledgement Log", h2))
    if not report["ops"]:
        story.append(Paragraph("No dispatch or acknowledgement actions recorded for this session.", body))
    else:
        rows = [["Time (s)", "Seat", "Action"]]
        for e in report["ops"]:
            rows.append([f"{e['sim_time']:.1f}", e["seat_id"].upper(), Paragraph(e.get("explanation") or "", body)])
        ops_table = Table(rows, colWidths=[0.7 * inch, 0.7 * inch, 5.5 * inch], repeatRows=1)
        ops_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(ops_table)

    story.append(Paragraph("Detection Methodology", h2))
    story.append(
        Paragraph(
            "Every alert above passed the same real accuracy pipeline before reaching this report — none are raw "
            "threshold crossings. A raw torso/motion deviation only becomes an alert once it clears a minimum "
            "sustained duration (not a single-frame flicker) and a deterministic prosecution/defense adjudication "
            "check (real corroboration such as a second signal, confirmed object detection, or a repeating pattern; "
            "vetoed by measured counter-evidence such as low detection confidence or this seat's own recent "
            "false-alarm history). A moderate-confidence object detection with no other corroboration is flagged "
            "for human verification rather than treated as confirmed. Every score is measured against that "
            "individual seat's own settling-window baseline — never a flat threshold shared across seats — so a "
            "naturally still student and a naturally fidgety one are never held to the same bar.",
            body,
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Identity is seat-anchored, not face-based, and no face-recognition model exists anywhere in this "
            "pipeline. Evidence clips are face-blurred before storage; every clip view is logged for audit "
            "purposes. This report itself is generated fresh from the live database at export time, not a cached "
            "or pre-written document.",
            meta_style,
        )
    )

    doc.build(story)
    return buf.getvalue()
