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
# it's the only source for historical risk-trend analytics). "dispatch" is
# Phase 4's audit trail for "who was sent to check on this seat, when" —
# same log_events path as everything else, not a separate table.
# "calibration_warning" (Part 2.5) is the repeated-same-direction-gesture
# signature, logged distinctly from "gesture_alert" so it's queryable/
# auditable as its own signal.
PERSISTED_TYPES = ("telemetry", "alert", "gesture_alert", "feedback", "dispatch", "calibration_warning", "acknowledge")


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


class FeedbackLabel(Base):
    """Product audit &sect;7.1 (2026-08-22): every alert resolution an
    invigilator already makes (false_alarm/confirmed/no_action) is a real
    three-way human label over a specific signal. Before this, that label
    only ever fed back into widening one seat's baseline threshold and was
    otherwise discarded — a year of real exam sessions run that way
    produces zero structured training data. This table persists the label
    itself: which kind of signal fired, at what confidence, and what a
    human said really happened — the same shape of row the roadmap's
    ST-GCN++ classifier and object-detector v2 retraining will eventually
    consume, available starting now instead of only once those exist."""

    __tablename__ = "feedback_labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    seat_id: Mapped[str] = mapped_column(String(50), index=True)
    signal_type: Mapped[str] = mapped_column(String(30), index=True)  # object|posture|motion|gesture
    object_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolution: Mapped[str] = mapped_column(String(20), index=True)  # false_alarm|confirmed|no_action
    invigilator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Evidence Vault (2026-08-23): the sim_time of the specific alert this
    # resolution was about. resolve_alert() only ever knew "this seat's
    # currently-open alert," never a specific EventLog row id — this is
    # what lets a caller match a resolution back to one exact evidence
    # clip (join on seat_id + sim_time within a couple seconds) instead of
    # only knowing a seat has SOME resolved alert somewhere.
    sim_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def log_feedback_label(
    session_id: int,
    seat_id: str,
    signal_type: str,
    resolution: str,
    object_label: Optional[str] = None,
    confidence: Optional[float] = None,
    invigilator: Optional[str] = None,
    sim_time: Optional[float] = None,
) -> None:
    with SessionLocal() as db:
        db.add(
            FeedbackLabel(
                session_id=session_id,
                seat_id=seat_id,
                signal_type=signal_type,
                object_label=object_label,
                confidence=confidence,
                resolution=resolution,
                invigilator=invigilator,
                sim_time=sim_time,
            )
        )
        db.commit()


def feedback_label_summary() -> dict:
    """Tally used by Analytics to show a real, growing count of structured
    human labels — the concrete "every hour of use produces more training
    data" claim, not a promise."""
    with SessionLocal() as db:
        total = db.execute(select(func.count()).select_from(FeedbackLabel)).scalar() or 0
        by_resolution = dict(
            db.execute(select(FeedbackLabel.resolution, func.count()).group_by(FeedbackLabel.resolution)).all()
        )
        by_signal = dict(
            db.execute(select(FeedbackLabel.signal_type, func.count()).group_by(FeedbackLabel.signal_type)).all()
        )
        recent_rows = db.execute(
            select(FeedbackLabel).order_by(FeedbackLabel.id.desc()).limit(20)
        ).scalars().all()
        return {
            "total_labels": int(total),
            "by_resolution": by_resolution,
            "by_signal_type": by_signal,
            "recent": [
                {
                    "seat_id": r.seat_id,
                    "signal_type": r.signal_type,
                    "object_label": r.object_label,
                    "confidence": r.confidence,
                    "resolution": r.resolution,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in recent_rows
            ],
        }


def evidence_vault_data(session_id: Optional[int] = None, seat_ids: Optional[list[str]] = None) -> dict:
    """Evidence Vault (2026-08-23): every clip plus its REAL resolution
    status, matched from the FeedbackLabel table by (seat_id, sim_time
    within 3s) — resolve_alert() only ever knew "this seat's open alert,"
    not a specific EventLog row, so this is a best-effort real match, not
    a guess pulled from nowhere. A clip with no matching label is
    genuinely unresolved, not a data gap. Also returns the real summary
    numbers the vault's new top panel shows — no number here is
    simulated, everything is a real count/average over what's actually in
    the database."""
    with SessionLocal() as db:
        clip_stmt = (
            select(EventLog)
            .where(EventLog.event_type == "alert", EventLog.evidence_url.isnot(None))
            .order_by(EventLog.id.desc())
        )
        if session_id is not None:
            clip_stmt = clip_stmt.where(EventLog.session_id == session_id)
        if seat_ids:
            clip_stmt = clip_stmt.where(EventLog.seat_id.in_(seat_ids))
        clips = db.execute(clip_stmt).scalars().all()

        label_stmt = select(FeedbackLabel)
        if session_id is not None:
            label_stmt = label_stmt.where(FeedbackLabel.session_id == session_id)
        labels = db.execute(label_stmt).scalars().all()
        labels_by_seat: dict[str, list[FeedbackLabel]] = {}
        for lbl in labels:
            labels_by_seat.setdefault(lbl.seat_id, []).append(lbl)

        clip_rows = []
        resolved_count = 0
        confirmed_count = 0
        false_alarm_count = 0
        no_action_count = 0
        confidences: list[float] = []
        for c in clips:
            match: Optional[FeedbackLabel] = None
            candidates = labels_by_seat.get(c.seat_id, [])
            if candidates:
                closest = min(candidates, key=lambda lbl: abs((lbl.sim_time or 1e9) - c.sim_time))
                if closest.sim_time is not None and abs(closest.sim_time - c.sim_time) <= 3.0:
                    match = closest
            resolution = match.resolution if match else None
            if resolution:
                resolved_count += 1
                if resolution == "confirmed":
                    confirmed_count += 1
                elif resolution == "false_alarm":
                    false_alarm_count += 1
                elif resolution == "no_action":
                    no_action_count += 1
            if c.confidence is not None:
                confidences.append(c.confidence)
            clip_rows.append(
                {
                    "id": c.id,
                    "seat_id": c.seat_id,
                    "sim_time": c.sim_time,
                    "explanation": c.explanation,
                    "evidence_url": c.evidence_url,
                    "risk_score": c.risk_score,
                    "confidence": c.confidence,
                    "object_label": c.object_label,
                    "resolution": resolution,
                }
            )

        total_labels = len(labels)
        return {
            "clips": clip_rows,
            "summary": {
                "total_clips": len(clips),
                "reviewed_count": resolved_count,
                "confirmed_count": confirmed_count,
                "false_alarm_count": false_alarm_count,
                "no_action_count": no_action_count,
                "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
                "training_labels_count": total_labels,
            },
        }


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_add_missing_columns()


def _migrate_add_missing_columns() -> None:
    """create_all() only creates tables that don't exist yet — it never
    alters an existing table's columns. feedback_labels was created
    earlier this same session (before sim_time was added to the model),
    so a fresh restart against the same data/db/kinesis.db file crashed
    every read/write of that table with "no such column: sim_time". This
    is a lightweight, idempotent ADD COLUMN pass for exactly that gap,
    not a general migration framework — fine for this project's SQLite
    dev/demo scale, not what a Postgres production deployment should
    still be using by then."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "feedback_labels" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("feedback_labels")}
    if "sim_time" not in existing_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE feedback_labels ADD COLUMN sim_time FLOAT"))


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
    seat_ids: Optional[list[str]] = None,
) -> list[dict]:
    """seat_ids (2026-08-23, efficiency pass): lets a caller with multiple
    seats to cover (e.g. the camera detail view's own alert history) get
    them in one query instead of N sequential ones — CameraDetailPage.tsx
    used to Promise.all one /api/events fetch per seat on this camera,
    which is N round trips and N SQLite queries for what's really one
    filter. seat_id (singular) is untouched for existing single-seat
    callers like SeatDetailPage."""
    with SessionLocal() as db:
        stmt = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        if session_id is not None:
            stmt = stmt.where(EventLog.session_id == session_id)
        if seat_ids:
            stmt = stmt.where(EventLog.seat_id.in_(seat_ids))
        elif seat_id:
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
        # Bug fix (2026-08-22, caught live while testing §7.1's new labeled-
        # feedback table): this used to count every EventLog row with
        # event_type == "feedback" — which fires on EVERY resolution
        # (false_alarm / confirmed / no_action alike) — while the UI it
        # feeds (SystemLearningIndicator) presented it as specifically
        # "false-positives dismissed." A "confirmed" resolution was
        # inflating a stat that's supposed to represent the opposite
        # outcome. Now counts real false_alarm resolutions from the
        # FeedbackLabel table (§7.1), which has an actual resolution
        # column instead of free-text needing to be pattern-matched.
        feedback_count_stmt = select(func.count()).select_from(FeedbackLabel).where(FeedbackLabel.resolution == "false_alarm")
        per_seat_stmt = (
            select(EventLog.seat_id, func.count())
            .where(EventLog.event_type.in_(["alert", "gesture_alert"]))
            .group_by(EventLog.seat_id)
        )
        if session_id is not None:
            alert_count_stmt = alert_count_stmt.where(EventLog.session_id == session_id)
            avg_risk_stmt = avg_risk_stmt.where(EventLog.session_id == session_id)
            feedback_count_stmt = feedback_count_stmt.where(FeedbackLabel.session_id == session_id)
            per_seat_stmt = per_seat_stmt.where(EventLog.session_id == session_id)
        if seat_ids:
            alert_count_stmt = alert_count_stmt.where(EventLog.seat_id.in_(seat_ids))
            avg_risk_stmt = avg_risk_stmt.where(EventLog.seat_id.in_(seat_ids))
            feedback_count_stmt = feedback_count_stmt.where(FeedbackLabel.seat_id.in_(seat_ids))
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
