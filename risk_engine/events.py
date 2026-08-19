"""Stage 7: rule-based event detection from baseline z-scores.

Runs in parallel with the ST-GCN++ behaviour classifier planned for Stage 8
(docs/architecture.md §6) — a permanent parallel signal, not a placeholder
to delete once ST-GCN exists. Detects sustained deviation from a seat's own
calibrated baseline: a z-score crossing that holds long enough to be a real
event, not a single noisy frame (accuracy checklist: never classify on one
frame, use temporal smoothing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DeviationEvent:
    seat_id: str
    start_time: float
    end_time: float
    peak_zscore: float
    signal: str  # "torso_yaw" or "motion"

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class SustainedDeviationDetector:
    """Tracks an in-progress deviation per (seat_id, signal) and emits a
    DeviationEvent once it ends, but only if it held above threshold for at
    least min_duration_seconds."""

    def __init__(self, zscore_threshold: float = 2.5, min_duration_seconds: float = 1.5):
        self.zscore_threshold = zscore_threshold
        self.min_duration_seconds = min_duration_seconds
        self._active: dict[tuple[str, str], dict] = {}

    def observe(
        self, seat_id: str, signal: str, timestamp: float, zscore: Optional[float]
    ) -> Optional[DeviationEvent]:
        key = (seat_id, signal)
        above = zscore is not None and abs(zscore) >= self.zscore_threshold

        if above:
            if key not in self._active:
                self._active[key] = {"start": timestamp, "peak": zscore}
            elif abs(zscore) > abs(self._active[key]["peak"]):
                self._active[key]["peak"] = zscore
            return None

        if key in self._active:
            state = self._active.pop(key)
            duration = timestamp - state["start"]
            if duration >= self.min_duration_seconds:
                return DeviationEvent(
                    seat_id=seat_id,
                    start_time=state["start"],
                    end_time=timestamp,
                    peak_zscore=state["peak"],
                    signal=signal,
                )
        return None
