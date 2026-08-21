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
    is_alert: bool = False  # Part B (2026-08-21): corroborated enough for a full alert, not just watch


class RiskEngine:
    def __init__(
        self,
        zscore_threshold: float = 2.5,
        min_event_duration: float = 1.5,
        pattern_window_seconds: float = 300.0,
        weight_deviation: float = 0.4,
        weight_pattern: float = 0.25,
        weight_object: float = 0.15,
        weight_gesture: float = 0.2,
        alert_min_duration: float = 3.5,
        alert_min_repeat_count: int = 2,
        alert_cap_when_uncorroborated: float = 0.45,
    ):
        self.detector = SustainedDeviationDetector(zscore_threshold, min_event_duration)
        self.pattern_tracker = EventPatternTracker(pattern_window_seconds)
        self.weight_deviation = weight_deviation
        self.weight_pattern = weight_pattern
        self.weight_object = weight_object
        self.weight_gesture = weight_gesture
        # Part B (2026-08-21 pre-demo hardening): min_event_duration (above)
        # is the floor for "is this even a real DeviationEvent" (debounces
        # single-frame noise) - confirmed via risk_engine/events.py that
        # this is a genuinely enforced code check, not just a UI label. But
        # audited alongside it: that floor alone was ALSO sufficient for a
        # full "alert" (dispatchable, evidence-capturing) with zero second
        # signal - a lone 1.5s torso/motion blip qualified. These three
        # constants raise the bar for "alert" specifically, without
        # touching "watch" sensitivity at all - see observe() below.
        self.alert_min_duration = alert_min_duration
        self.alert_min_repeat_count = alert_min_repeat_count
        self.alert_cap_when_uncorroborated = alert_cap_when_uncorroborated

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
        gesture_active: bool = False,
    ) -> RiskAssessment:
        """gesture_active: a behaviour/gestures.py GestureDetector event
        (e.g. hand_reach_across) completed for this seat on this frame —
        already validated (sustained-duration filtered, calibration-issue
        pattern excluded) by that module, not a raw signal needing its own
        z-score. Found via a real gap (2026-08-21): gesture events were
        pushed straight to the UI event feed but never reached this engine,
        so a student repeatedly reaching across never elevated risk_score
        or the seat card's status color."""
        event: Optional[DeviationEvent] = None
        for signal, z in (("torso_yaw", yaw_zscore), ("motion", motion_zscore)):
            emitted = self.detector.observe(seat_id, signal, timestamp, z)
            if emitted is not None:
                event = emitted
                self.pattern_tracker.add(event)

        if gesture_active:
            # Feed the SAME pattern tracker used for yaw/motion deviations,
            # so "reached across 3 times in 5 minutes" scores worse than
            # once — this module's existing isolated-event-vs-pattern
            # philosophy, extended to gestures. Deliberately NOT assigned to
            # `event` below: explain_event()'s template is written for a
            # z-score deviation from baseline (mean±std), which doesn't
            # apply to a gesture; behaviour/gestures.py's own
            # explain_gesture() already produces the correct text for the
            # separate gesture_alert event the UI receives.
            self.pattern_tracker.add(
                DeviationEvent(
                    seat_id=seat_id, start_time=timestamp, end_time=timestamp,
                    peak_zscore=self.detector.zscore_threshold, signal="gesture",
                )
            )

        deviation_component = 0.0
        for z in (yaw_zscore, motion_zscore):
            if z is not None:
                deviation_component = max(deviation_component, min(abs(z) / 5.0, 1.0))

        pattern_component = min(self.pattern_tracker.pattern_score(seat_id, timestamp) / 3.0, 1.0)
        object_component = object_confidence if object_label else 0.0
        gesture_component = 1.0 if gesture_active else 0.0

        risk_score = (
            self.weight_deviation * deviation_component
            + self.weight_pattern * pattern_component
            + self.weight_object * object_component
            + self.weight_gesture * gesture_component
        )

        # Part B (2026-08-21 pre-demo hardening): a completed DeviationEvent
        # only qualifies as a genuine "alert" — not just "watch" — when
        # corroborated. "torso_yaw" (head/body rotation) maps to the PS's
        # own named behaviours ("excessive head turning", "body rotation
        # toward neighbouring students"), so sustained duration alone can
        # still qualify it, provided that duration clears the stricter
        # alert_min_duration bar (not just the 1.5s floor for "is this a
        # real event at all"). "motion" (movement level) doesn't map to any
        # specific named PS behaviour on its own — could be entirely
        # innocuous (stretching, settling in) — so it NEVER qualifies by
        # duration alone, only when corroborated by something else.
        # Object detection, a concurrent gesture, or the pattern tracker
        # confirming this isn't the first occurrence in the window all
        # count as corroboration for either signal.
        is_alert = False
        if event is not None:
            corroborated_by_object = object_label is not None
            corroborated_by_gesture = gesture_active
            corroborated_by_pattern = self.pattern_tracker.event_count(seat_id, timestamp) >= self.alert_min_repeat_count
            corroborated_by_duration = event.signal == "torso_yaw" and event.duration >= self.alert_min_duration
            is_alert = corroborated_by_duration or corroborated_by_object or corroborated_by_gesture or corroborated_by_pattern
            if not is_alert:
                # Uncorroborated single deviation: keep it visible as
                # "watch" (below is capped just under the alert threshold),
                # never escalate to "alert" - sensitivity isn't lost, only
                # the standalone-alert claim is.
                risk_score = min(risk_score, self.alert_cap_when_uncorroborated)

        explanation = None
        if event is not None:
            explanation = explain_event(event, baseline_yaw_mean, baseline_yaw_std, object_label)

        return RiskAssessment(
            seat_id=seat_id, risk_score=risk_score, explanation=explanation, triggering_event=event, is_alert=is_alert
        )
