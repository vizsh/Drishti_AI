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

from risk_engine.adjudication import Finding, adjudicate
from risk_engine.events import DeviationEvent, SustainedDeviationDetector
from risk_engine.explain import explain_event, explain_object_only
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
    # Part 2b: the deterministic prosecution/defense checklist behind
    # is_alert above — empty on frames with no completed DeviationEvent.
    prosecution: list[Finding] = None  # type: ignore[assignment]
    defense: list[Finding] = None  # type: ignore[assignment]
    # Accuracy audit (2026-08-22): True when this alert's ONLY corroboration
    # is object detection with no motion/yaw/gesture co-signal at all, at a
    # confidence below object_alert_high_confidence. The stock object
    # detector genuinely confuses some real background objects for
    # contraband at moderate confidence (confirmed against real footage,
    # data/test_videos/04 -- a static water bottle read as "cell phone" at
    # 0.15-0.31 for an entire 143s clip) in a band that overlaps real
    # detections too closely to separate by confidence alone. Rather than
    # silently trust or silently drop a borderline case, it's still logged
    # and shown, but flagged for a human to look rather than pushed as a
    # confident, auto-notify alert (see PipelineWorker's notify gating).
    needs_verification: bool = False

    def __post_init__(self) -> None:
        if self.prosecution is None:
            self.prosecution = []
        if self.defense is None:
            self.defense = []


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
        object_alert_min_duration: float = 2.0,
        object_alert_high_confidence: float = 0.5,
        exam_type: str = "mixed",
    ):
        self.detector = SustainedDeviationDetector(zscore_threshold, min_event_duration)
        self.pattern_tracker = EventPatternTracker(pattern_window_seconds)
        # Accuracy audit (2026-08-22): a confirmed contraband object used to
        # only ever matter as a corroborator of a torso/motion deviation
        # event -- if no such event happened to complete, object detection
        # (however clearly confirmed) was silently discarded. Ground-truth
        # audit (data/test_videos/01) found exactly this: a real phone,
        # confirmed present for 15+ continuous seconds, produced zero
        # alerts, because the student wasn't also moving enough to trip a
        # z-score event at the same time. This constant gates a SEPARATE
        # trigger path (see observe() below) that lets a confirmed object
        # alert on its own once it's been persistently detected for this
        # long -- 2.0s, matched to ObjectPersistenceTracker's own 2-hit
        # requirement, so this duration is never shorter than what
        # "confirmed" already means.
        self.object_alert_min_duration = object_alert_min_duration
        # Accuracy audit (2026-08-22): below this confidence, an object-
        # only alert (no motion/yaw/gesture at all) is still raised and
        # logged but flagged needs_verification=True instead of pushed as
        # a confident notification -- see RiskAssessment.needs_verification.
        self.object_alert_high_confidence = object_alert_high_confidence
        # Per-seat: has the CURRENT confirmed-object streak already been
        # evaluated for an alert? Reset the moment the object stops being
        # confirmed, so a new appearance gets its own fresh evaluation
        # instead of firing a new alert every single frame the object stays
        # in view (the exact flooding this whole audit exists to stop).
        self._object_streak_evaluated: dict[str, bool] = {}
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
        object_duration: float = 0.0,
        gesture_active: bool = False,
        object_class_verified: bool = True,
        fused_confidence: float = 1.0,
        camera_needs_attention: bool = False,
        recent_false_alarm_count: int = 0,
        recent_calibration_warning: bool = False,
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

        # Part B/2b (2026-08-21): a completed DeviationEvent only qualifies
        # as a genuine "alert" — not just "watch" — when a deterministic
        # prosecution/defense adjudication (risk_engine/adjudication.py)
        # both (a) clears a real corroboration bar and (b) isn't vetoed by
        # measured counter-evidence (low confidence, a camera needing
        # attention, this seat's own false-positive history, an unverified
        # detector as the sole corroboration, or a known calibration-issue
        # signature). Every finding is surfaced to the invigilator UI
        # alongside the plain-language explanation — never hidden reasoning.
        is_alert = False
        prosecution: list[Finding] = []
        defense: list[Finding] = []
        explanation: Optional[str] = None
        triggering_event = event
        needs_verification = False

        # Reset the object-alert streak tracker the moment the object isn't
        # confirmed anymore, so its next appearance is evaluated fresh.
        if object_label is None:
            self._object_streak_evaluated[seat_id] = False

        if event is not None:
            self._object_streak_evaluated[seat_id] = True  # handled via the event path below, don't also fire object-only
            event.independently_corroborated = (
                (event.signal == "torso_yaw" and event.duration >= self.alert_min_duration)
                or object_label is not None
                or gesture_active
            )
            result = adjudicate(
                event_signal=event.signal,
                event_duration=event.duration,
                alert_min_duration=self.alert_min_duration,
                object_label=object_label,
                object_confidence=object_confidence,
                object_class_verified=object_class_verified,
                gesture_active=gesture_active,
                pattern_event_count=self.pattern_tracker.event_count(seat_id, timestamp),
                pattern_independently_corroborated_count=self.pattern_tracker.independently_corroborated_count(seat_id, timestamp),
                alert_min_repeat_count=self.alert_min_repeat_count,
                fused_confidence=fused_confidence,
                camera_needs_attention=camera_needs_attention,
                recent_false_alarm_count=recent_false_alarm_count,
                recent_calibration_warning=recent_calibration_warning,
            )
            is_alert = result.is_alert
            prosecution = result.prosecution
            defense = result.defense
            explanation = explain_event(event, baseline_yaw_mean, baseline_yaw_std, object_label)
        elif object_label is not None and object_duration >= self.object_alert_min_duration:
            # Object-only trigger path (accuracy audit, 2026-08-22): fires
            # once per confirmed-object streak, independent of any z-score
            # deviation -- see this module's __init__ docstring on
            # object_alert_min_duration for why this path exists at all.
            already_evaluated = self._object_streak_evaluated.get(seat_id, False)
            self._object_streak_evaluated[seat_id] = True
            if not already_evaluated:
                synthetic_event = DeviationEvent(
                    seat_id=seat_id,
                    start_time=timestamp - object_duration,
                    end_time=timestamp,
                    peak_zscore=0.0,
                    signal="object",
                )
                result = adjudicate(
                    event_signal="object",
                    event_duration=object_duration,
                    alert_min_duration=self.alert_min_duration,
                    object_label=object_label,
                    object_confidence=object_confidence,
                    object_class_verified=object_class_verified,
                    gesture_active=gesture_active,
                    pattern_event_count=self.pattern_tracker.event_count(seat_id, timestamp),
                    pattern_independently_corroborated_count=self.pattern_tracker.independently_corroborated_count(seat_id, timestamp),
                    alert_min_repeat_count=self.alert_min_repeat_count,
                    fused_confidence=fused_confidence,
                    camera_needs_attention=camera_needs_attention,
                    recent_false_alarm_count=recent_false_alarm_count,
                    recent_calibration_warning=recent_calibration_warning,
                )
                is_alert = result.is_alert
                prosecution = result.prosecution
                defense = result.defense
                triggering_event = synthetic_event
                explanation = explain_object_only(seat_id, object_label, object_confidence, object_duration)
                needs_verification = is_alert and object_confidence < self.object_alert_high_confidence

        if (event is not None or triggering_event is not None) and not is_alert:
            # Uncorroborated/vetoed single deviation: keep it visible as
            # "watch" (below is capped just under the alert threshold),
            # never escalate to "alert" - sensitivity isn't lost, only
            # the standalone-alert claim is.
            risk_score = min(risk_score, self.alert_cap_when_uncorroborated)

        return RiskAssessment(
            seat_id=seat_id,
            risk_score=risk_score,
            explanation=explanation,
            triggering_event=triggering_event,
            is_alert=is_alert,
            prosecution=prosecution,
            defense=defense,
            needs_verification=needs_verification,
        )
