"""Phase 6: Session Report export - a real PDF built from this session's
actual event log (backend/db.py), not a static template. Pulls fresh data
at export time: analytics summary, the full alert list (each correlated
with whatever dispatch/resolution followed it for that seat, if any), and
evidence references. reportlab renders directly to bytes in memory - no
temp files, no external renderer.
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
    "false_alarm": "False alarm (baseline widened)",
    "confirmed": "Confirmed issue",
    "no_action": "No action taken",
}


def _find_resolution(seat_events: list[dict], alert_time: float) -> Optional[str]:
    """Best-effort correlation: the nearest feedback event for this seat
    that came at or after the alert's sim_time. The data model logs
    dispatch/feedback as independent seat-scoped events (not linked to a
    specific alert id), so this is a real but approximate join - exact
    linkage would need a schema change beyond what Phase 6 asked for."""
    candidates = [e for e in seat_events if e["event_type"] == "feedback" and e["sim_time"] >= alert_time]
    if not candidates:
        return None
    nearest = min(candidates, key=lambda e: e["sim_time"] - alert_time)
    text = (nearest.get("explanation") or "").lower()
    if "false positive" in text or "widened" in text:
        return RESOLUTION_LABELS["false_alarm"]
    if "confirmed" in text:
        return RESOLUTION_LABELS["confirmed"]
    if "no action" in text:
        return RESOLUTION_LABELS["no_action"]
    return nearest.get("explanation")


def generate_session_report_pdf(session_id: Optional[int], seat_ids: Optional[list[str]] = None) -> bytes:
    analytics = db.analytics_summary(session_id, seat_ids)
    events = db.query_events(session_id=session_id, limit=5000)
    if seat_ids:
        seat_set = set(seat_ids)
        events = [e for e in events if e["seat_id"] in seat_set]

    events.sort(key=lambda e: e["sim_time"])
    alerts = [e for e in events if e["event_type"] in ("alert", "gesture_alert")]
    by_seat: dict[str, list[dict]] = {}
    for e in events:
        by_seat.setdefault(e["seat_id"], []).append(e)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.6 * inch, rightMargin=0.6 * inch
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("KTitle", parent=styles["Title"], fontSize=18, spaceAfter=4)
    meta_style = ParagraphStyle("KMeta", parent=styles["Normal"], textColor=colors.grey, fontSize=9)
    h2 = ParagraphStyle("KH2", parent=styles["Heading2"], spaceBefore=16, spaceAfter=6)
    body = ParagraphStyle("KBody", parent=styles["Normal"], fontSize=9, leading=12)

    story = [
        Paragraph("KINESIS AI — Session Report", title_style),
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            f"{' · scoped to ' + ', '.join(sorted(seat_ids)) if seat_ids else ' · all monitored seats'}",
            meta_style,
        ),
        Spacer(1, 14),
        Paragraph("Summary", h2),
    ]

    summary_rows = [
        ["Total alerts", str(analytics["total_alerts"])],
        ["Average risk score", f"{analytics['avg_risk']:.3f}"],
        ["False positives dismissed (baseline adaptations)", str(analytics["false_positives_dismissed"])],
        ["Seats with alert activity", str(len(analytics["alerts_per_seat"]))],
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

    story.append(Paragraph("Alert Log", h2))
    if not alerts:
        story.append(Paragraph("No alerts recorded for this session.", body))
    else:
        header = ["Time (s)", "Seat", "Explanation", "Resolution", "Evidence"]
        rows = [header]
        for a in alerts:
            resolution = _find_resolution(by_seat.get(a["seat_id"], []), a["sim_time"]) or "Unresolved"
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

    story.append(Paragraph("Dispatch & Resolution Log", h2))
    ops_events = [e for e in events if e["event_type"] in ("dispatch", "feedback")]
    if not ops_events:
        story.append(Paragraph("No dispatch or resolution actions recorded for this session.", body))
    else:
        rows = [["Time (s)", "Seat", "Action"]]
        for e in ops_events:
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

    story.append(Spacer(1, 16))
    story.append(
        Paragraph(
            "Identity is seat-anchored, not face-based. Risk is scored against each student's own calibrated "
            "baseline, not a fixed threshold. Evidence clips are face-blurred before storage; every clip view is "
            "logged for audit purposes.",
            meta_style,
        )
    )

    doc.build(story)
    return buf.getvalue()
