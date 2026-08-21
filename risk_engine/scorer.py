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

# Part G Tier 1 (2026-08-21): exam-type weight profiles. yaw/motion used to
# share one "deviation" weight (whichever z-score was larger dominated) -
# split apart here specifically so MCQ and Written can weight them
# differently, per the reasoning each profile's comment gives. All five
# weights per profile sum to 1.0; "mixed" reproduces the old undifferentiated
# behaviour (yaw and motion each get half of the old 0.4 weight_deviation).
EXAM_TYPE_PROFILES: dict[str, dict[str, float]] = {
    "mixed": {"weight_yaw": 0.20, "weight_motion": 0.20, "weight_pattern": 0.25, "weight_object": 0.15, "weight_gesture": 0.20},
    "mcq": {
        # Marking answers is brief/periodic hand motion - SUSTAINED or
        # REPEATED hand movement (gesture, and motion staying elevated
        # rather than briefly spiking) is more anomalous here than in a
        # written exam, so both go up. A single glance can copy an MCQ
        # answer, so gaze/head-turn (yaw) also weights higher. Object
        # detection (paper/chit) matters less for an exam with no paper.
        "weight_yaw": 0.30, "weight_motion": 0.20, "weight_pattern": 0.15, "weight_object": 0.05, "weight_gesture": 0.30,
    },
    "written": {
        # Hand motion is near-constant (writing) and uninformative on its
        # own - weight way down. Weight shifts to sustained gaze/head-turn
        # (yaw), object detection (a written exam has actual paper on the
        # desk, so paper/chit-passing signals are meaningful here in a way
        # they aren't for MCQ), and the pattern tracker (repeated behaviour
        # over the session matters more than a single blip either way).
        "weight_yaw": 0.30, "weight_motion": 0.05, "weight_pattern": 0.20, "weight_object": 0.35, "weight_gesture": 0.10,
    },
}


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
        zscore_threshold: float = 3.5,
        min_event_duration: float = 1.5,
        pattern_window_seconds: float = 300.0,
        weight_yaw: float = 0.20,
        weight_motion: float = 0.20,
        weight_pattern: float = 0.25,
        weight_object: float = 0.15,
        weight_gesture: float = 0.20,
        alert_min_duration: float = 8.0,
        alert_min_repeat_count: int = 2,
        alert_cap_when_uncorroborated: float = 0.45,
        exam_type: str = "mixed",
    ):
        self.detector = SustainedDeviationDetector(zscore_threshold, min_event_duration)
        self.pattern_tracker = EventPatternTracker(pattern_window_seconds)
        self.weight_yaw = weight_yaw
        self.weight_motion = weight_motion
        self.weight_pattern = weight_pattern
        self.weight_object = weight_object
        self.weight_gesture = weight_gesture
        self.exam_type = exam_type
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

    def apply_profile(self, exam_type: str) -> None:
        """Part G Tier 1: swaps the five signal weights to the named exam-
        type profile in place — keeps the detector/pattern_tracker's
        in-progress state (an in-flight deviation, recent event history)
        intact, since this only changes how signals are WEIGHTED, not
        what's been observed so far this session."""
        profile = EXAM_TYPE_PROFILES.get(exam_type, EXAM_TYPE_PROFILES["mixed"])
        self.weight_yaw = profile["weight_yaw"]
        self.weight_motion = profile["weight_motion"]
        self.weight_pattern = profile["weight_pattern"]
        self.weight_object = profile["weight_object"]
        self.weight_gesture = profile["weight_gesture"]
        self.exam_type = exam_type if exam_type in EXAM_TYPE_PROFILES else "mixed"

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

        # Part G Tier 1: yaw and motion weighted separately (used to share
        # one "deviation" weight via max(), so a profile could never make
        # them differ) - lets the exam-type profile push them apart.
        yaw_component = min(abs(yaw_zscore) / 5.0, 1.0) if yaw_zscore is not None else 0.0
        motion_component = min(abs(motion_zscore) / 5.0, 1.0) if motion_zscore is not None else 0.0

        pattern_component = min(self.pattern_tracker.pattern_score(seat_id, timestamp) / 3.0, 1.0)
        object_component = object_confidence if object_label else 0.0
        gesture_component = 1.0 if gesture_active else 0.0

        risk_score = (
            self.weight_yaw * yaw_component
            + self.weight_motion * motion_component
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
