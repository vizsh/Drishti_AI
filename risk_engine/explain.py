"""Stage 7/10: deterministic, template-based alert explanations
(docs/architecture.md §10) — built from measured features, never
generative. Auditable: every clause traces to a number a human can verify,
and it can't hallucinate a reason that didn't happen.
"""

from __future__ import annotations

from typing import Optional

from risk_engine.events import DeviationEvent

_SIGNAL_NAMES = {"torso_yaw": "Torso orientation", "motion": "Movement level"}


def explain_event(
    event: DeviationEvent, baseline_mean: float, baseline_std: float, object_label: Optional[str]
) -> str:
    signal_name = _SIGNAL_NAMES.get(event.signal, event.signal)
    magnitude = abs(event.peak_zscore)
    object_clause = f"{object_label} detected" if object_label else "no object detected"
    return (
        f"{signal_name} deviated {magnitude:.1f}x from {event.seat_id}'s baseline "
        f"for {event.duration:.1f}s (baseline {baseline_mean:+.2f}±{baseline_std:.2f}). "
        f"{object_clause.capitalize()}."
    )
