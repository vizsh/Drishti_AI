"""Stage 7: risk fusion engine (docs/architecture.md §7).

Deterministic weighted combination of baseline z-score deviation +
rule-based event/pattern scoring + object-detection confidence. No ML model
here by design — explainability requires every risk number to trace back to
a measured feature (risk_engine/explain.py), not a black box.

Hand-tuned weights, upgradeable to a small logistic regression later if
labeled "was this actually suspicious" data exists — explicitly deferred
per docs/architecture.md §7 since no such data exists yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from risk_engine.events import DeviationEvent, SustainedDeviationDetector
from risk_engine.explain import explain_event
from risk_engine.pattern import EventPatternTracker


@dataclass
class RiskAssessment:
    seat_id: str
    risk_score: float  # roughly 0.0-1.0, unbounded above under repeated events
    explanation: Optional[str]
    triggering_event: Optional[DeviationEvent]


class RiskEngine:
    def __init__(
        self,
        zscore_threshold: float = 2.5,
        min_event_duration: float = 1.5,
        pattern_window_seconds: float = 300.0,
        weight_deviation: float = 0.5,
        weight_pattern: float = 0.3,
        weight_object: float = 0.2,
    ):
        self.detector = SustainedDeviationDetector(zscore_threshold, min_event_duration)
        self.pattern_tracker = EventPatternTracker(pattern_window_seconds)
        self.weight_deviation = weight_deviation
        self.weight_pattern = weight_pattern
        self.weight_object = weight_object

    def observe(
        self,
        seat_id: str,
        timestamp: float,
        yaw_zscore: Optional[float],
        motion_zscore: Optional[float],
        baseline_yaw_mean: float = 0.0,
        baseline_yaw_std: float = 0.0,
        object_label: Optional[str] = None,
        object_confidence: float = 0.0,
    ) -> RiskAssessment:
        event: Optional[DeviationEvent] = None
        for signal, z in (("torso_yaw", yaw_zscore), ("motion", motion_zscore)):
            emitted = self.detector.observe(seat_id, signal, timestamp, z)
            if emitted is not None:
                event = emitted
                self.pattern_tracker.add(event)

        deviation_component = 0.0
        for z in (yaw_zscore, motion_zscore):
            if z is not None:
                deviation_component = max(deviation_component, min(abs(z) / 5.0, 1.0))

        pattern_component = min(self.pattern_tracker.pattern_score(seat_id, timestamp) / 3.0, 1.0)
        object_component = object_confidence if object_label else 0.0

        risk_score = (
            self.weight_deviation * deviation_component
            + self.weight_pattern * pattern_component
            + self.weight_object * object_component
        )

        explanation = None
        if event is not None:
            explanation = explain_event(event, baseline_yaw_mean, baseline_yaw_std, object_label)

        return RiskAssessment(seat_id=seat_id, risk_score=risk_score, explanation=explanation, triggering_event=event)
