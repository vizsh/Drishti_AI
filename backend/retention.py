"""Data retention enforcement (product audit, 2026-08-22).

Closes the one gap the Trust & Compliance page has openly admitted since
before this session: "This system currently keeps all session data...
indefinitely; there is no automatic deletion... That retention policy is
not yet enforced by the software itself." This is the enforcement --
evidence clips and old event-log rows past retention_days are actually
deleted, not just described as a policy an institution should adopt.

Age is measured off real wall-clock time (the evidence clip directory's
filesystem mtime, and EventLog.created_at, both already real UTC
timestamps) -- never sim_time, which is a per-session synthetic clock and
means nothing across sessions or after a restart.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from backend import db
from backend.evidence import EVIDENCE_DIR

DEFAULT_RETENTION_DAYS = 90
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650  # 10 years -- a ceiling against a fat-fingered "forever" that silently means the sweep never fires meaningfully differently from "off"


def run_retention_sweep(retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """Deletes evidence clips whose directory is older than retention_days,
    and prunes EventLog/EvidenceAccessLog rows past the same cutoff.
    Returns real counts of what was actually removed -- callers (the
    /api/settings/retention endpoint, the startup sweep) should surface
    this, not just report "sweep ran"."""
    cutoff_wall = time.time() - retention_days * 86400
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)

    deleted_clips: list[str] = []
    if EVIDENCE_DIR.exists():
        for clip_dir in EVIDENCE_DIR.iterdir():
            if not clip_dir.is_dir():
                continue
            if clip_dir.stat().st_mtime < cutoff_wall:
                shutil.rmtree(clip_dir, ignore_errors=True)
                deleted_clips.append(clip_dir.name)

    with db.SessionLocal() as session:
        events_result = session.execute(delete(db.EventLog).where(db.EventLog.created_at < cutoff_dt))
        access_result = session.execute(delete(db.EvidenceAccessLog).where(db.EvidenceAccessLog.accessed_at < cutoff_dt))
        session.commit()

    return {
        "retention_days": retention_days,
        "deleted_evidence_clips": len(deleted_clips),
        "deleted_event_rows": events_result.rowcount,
        "deleted_access_log_rows": access_result.rowcount,
        "swept_at": datetime.now(timezone.utc).isoformat(),
    }
