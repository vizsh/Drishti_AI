"""Persistent event-log storage — PS #1 objective: "provide behavioral
analytics and event logs for invigilator review." Alerts/telemetry were
in-memory-only before this (lost on refresh or restart), which didn't
actually satisfy that objective despite everything upstream being real.

SQLAlchemy over SQLite by default (zero-setup, a file at data/db/kinesis.db)
rather than requiring a running Postgres server, which isn't installed in
this dev environment. Swap DATABASE_URL to a Postgres DSN for the
production target from docs/architecture.md §11 — the schema and every
query below are portable, only the connection string changes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_PATH = Path("data/db/kinesis.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if IS_SQLITE else {})
SessionLocal = sessionmaker(bind=engine)

# Persisted event types: alerts/gestures/feedback are what invigilator
# review actually needs; telemetry is also kept (lower value per-row, but
# it's the only source for historical risk-trend analytics).
PERSISTED_TYPES = ("telemetry", "alert", "gesture_alert", "feedback")


class Base(DeclarativeBase):
    pass


class ExamSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_source: Mapped[str] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EvidenceAccessLog(Base):
    """PS risk table row "Privacy Concerns": evidence clips are the one
    raw-video artifact allowed off the edge boundary, so every view of one
    must be attributable — who looked at which clip, when. Logged
    server-side regardless of what the viewer's UI shows."""

    __tablename__ = "evidence_access_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[str] = mapped_column(String(200), index=True)
    client_ip: Mapped[str] = mapped_column(String(64))
    accessed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def log_evidence_access(clip_id: str, client_ip: str) -> None:
    with SessionLocal() as db:
        db.add(EvidenceAccessLog(clip_id=clip_id, client_ip=client_ip))
        db.commit()


def query_evidence_access(clip_id: Optional[str] = None, limit: int = 200) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(EvidenceAccessLog).order_by(EvidenceAccessLog.id.desc()).limit(limit)
        if clip_id:
            stmt = stmt.where(EvidenceAccessLog.clip_id == clip_id)
        rows = db.execute(stmt).scalars().all()
        return [
            {"id": r.id, "clip_id": r.clip_id, "client_ip": r.client_ip, "accessed_at": r.accessed_at.isoformat()}
            for r in rows
        ]


class EventLog(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    seat_id: Mapped[str] = mapped_column(String(50), index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    sim_time: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    yaw_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    motion_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    object_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def create_session(video_source: str) -> int:
    with SessionLocal() as db:
        s = ExamSession(video_source=video_source)
        db.add(s)
        db.commit()
        db.refresh(s)
        return s.id


def log_events(session_id: int, events: list[dict]) -> None:
    rows = []
    for ev in events:
        et = ev.get("type")
        if et not in PERSISTED_TYPES:
            continue
        rows.append(
            EventLog(
                session_id=session_id,
                seat_id=ev.get("seat_id", ""),
                event_type=et,
                sim_time=ev.get("timestamp", 0.0),
                risk_score=ev.get("risk_score"),
                yaw_z=ev.get("yaw_z"),
                motion_z=ev.get("motion_z"),
                object_label=ev.get("object_label"),
                explanation=ev.get("explanation") or ev.get("message"),
                evidence_url=ev.get("evidence_url"),
                confidence=ev.get("confidence"),
            )
        )
    if not rows:
        return
    with SessionLocal() as db:
        db.add_all(rows)
        db.commit()


def query_events(
    session_id: Optional[int] = None,
    seat_id: Optional[str] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        if session_id is not None:
            stmt = stmt.where(EventLog.session_id == session_id)
        if seat_id:
            stmt = stmt.where(EventLog.seat_id == seat_id)
        if event_type:
            stmt = stmt.where(EventLog.event_type == event_type)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(EventLog.explanation.like(pattern))
        rows = db.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "seat_id": r.seat_id,
                "event_type": r.event_type,
                "sim_time": r.sim_time,
                "risk_score": r.risk_score,
                "yaw_z": r.yaw_z,
                "motion_z": r.motion_z,
                "object_label": r.object_label,
                "explanation": r.explanation,
                "evidence_url": r.evidence_url,
                "confidence": r.confidence,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def analytics_summary(session_id: Optional[int] = None, seat_ids: Optional[list[str]] = None) -> dict:
    """seat_ids: optional hall-scoping filter (Phase 1 — role-based scoping
    must apply consistently, including the top-level stat strip, not just
    the seat grid/camera views)."""
    with SessionLocal() as db:
        alert_count_stmt = select(func.count()).select_from(EventLog).where(EventLog.event_type.in_(["alert", "gesture_alert"]))
        avg_risk_stmt = select(func.avg(EventLog.risk_score)).where(EventLog.event_type == "telemetry")
        feedback_count_stmt = select(func.count()).select_from(EventLog).where(EventLog.event_type == "feedback")
        per_seat_stmt = (
            select(EventLog.seat_id, func.count())
            .where(EventLog.event_type.in_(["alert", "gesture_alert"]))
            .group_by(EventLog.seat_id)
        )
        if session_id is not None:
            alert_count_stmt = alert_count_stmt.where(EventLog.session_id == session_id)
            avg_risk_stmt = avg_risk_stmt.where(EventLog.session_id == session_id)
            feedback_count_stmt = feedback_count_stmt.where(EventLog.session_id == session_id)
            per_seat_stmt = per_seat_stmt.where(EventLog.session_id == session_id)
        if seat_ids:
            alert_count_stmt = alert_count_stmt.where(EventLog.seat_id.in_(seat_ids))
            avg_risk_stmt = avg_risk_stmt.where(EventLog.seat_id.in_(seat_ids))
            feedback_count_stmt = feedback_count_stmt.where(EventLog.seat_id.in_(seat_ids))
            per_seat_stmt = per_seat_stmt.where(EventLog.seat_id.in_(seat_ids))

        alert_count = db.execute(alert_count_stmt).scalar() or 0
        avg_risk = db.execute(avg_risk_stmt).scalar() or 0.0
        feedback_count = db.execute(feedback_count_stmt).scalar() or 0
        per_seat = dict(db.execute(per_seat_stmt).all())

        return {
            "total_alerts": int(alert_count),
            "avg_risk": round(float(avg_risk), 3),
            "alerts_per_seat": per_seat,
            "false_positives_dismissed": int(feedback_count),
        }
