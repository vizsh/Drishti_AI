"""Part 2b (2026-08-21): deterministic, auditable two-sided evidence
adjudication for the risk fusion engine's is_alert decision.

Reproduced gap (Part 2a, see tools/repro_small_motion_alert.py): a seat
with ordinary, properly-calibrated small motion that happened to cross the
z-score threshold twice within the 5-minute pattern window was becoming a
full "alert" purely because the two uncorroborated motion blips
corroborated EACH OTHER via EventPatternTracker.event_count() — neither
blip ever had independent evidence (object detection, gesture, or a
sustained torso_yaw duration). That's the same weak signal counted twice,
not real corroboration, and it directly contradicted this engine's own
stated design intent that motion never qualifies "only when corroborated
by something else."

This module is a deterministic, inspectable checklist — NOT a generative/
LLM explanation (CLAUDE.md's non-negotiable constraint: every alert must
carry a template-based explanation built from measured features). Every
finding here is a direct readout of a signal already computed elsewhere in
the pipeline (risk_engine/events.py, risk_engine/pattern.py,
calibration/quality.py, behaviour/gestures.py, PipelineWorker's own
false-alarm/calibration-warning history). "Prosecution"/"defense" is a
framing for two sides of one fixed checklist, not two models debating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Finding:
    signal: str  # short machine-stable key, e.g. "object_detection"
    label: str  # human-readable one-liner for the invigilator UI
    detail: str  # the actual measured numbers behind the claim
    disqualifying: bool = False  # only set on the defense side


@dataclass
class AdjudicationResult:
    is_alert: bool
    prosecution: list[Finding]
    defense: list[Finding]


def adjudicate(
    *,
    event_signal: str,
    event_duration: float,
    alert_min_duration: float,
    object_label: Optional[str],
    object_confidence: float,
    object_class_verified: bool,
    gesture_active: bool,
    pattern_event_count: int,
    pattern_independently_corroborated_count: int,
    alert_min_repeat_count: int,
    fused_confidence: float,
    camera_needs_attention: bool,
    recent_false_alarm_count: int,
    recent_calibration_warning: bool,
    low_confidence_threshold: float = 0.5,
) -> AdjudicationResult:
    prosecution: list[Finding] = []
    defense: list[Finding] = []

    # --- Prosecution: every measured signal that corroborates this event ---
    corroborated_by_duration = event_signal == "torso_yaw" and event_duration >= alert_min_duration
    if corroborated_by_duration:
        prosecution.append(Finding(
            "sustained_duration",
            "Sustained head/body rotation, on its own, held long enough to qualify.",
            f"torso_yaw deviation held {event_duration:.1f}s (bar: {alert_min_duration:.1f}s)",
        ))

    corroborated_by_object = object_label is not None
    if corroborated_by_object:
        prosecution.append(Finding(
            "object_detection",
            f"A {object_label} was detected near this seat at the same time.",
            f"label={object_label}, confidence={object_confidence:.2f}",
        ))

    if gesture_active:
        prosecution.append(Finding(
            "gesture",
            "A validated hand-reach/gesture event completed for this seat at the same time.",
            "gesture_active=True (already duration- and calibration-pattern-filtered)",
        ))

    # The fix: pattern corroboration only counts when at least one of the
    # events in the window had independent evidence of its own — two
    # uncorroborated blips of the same weak signal no longer corroborate
    # each other into an alert.
    corroborated_by_pattern = (
        pattern_event_count >= alert_min_repeat_count
        and pattern_independently_corroborated_count >= 1
    )
    if pattern_event_count >= alert_min_repeat_count:
        if corroborated_by_pattern:
            prosecution.append(Finding(
                "repeated_pattern",
                f"{pattern_event_count} deviation events for this seat in the last 5 minutes, at least one independently corroborated.",
                f"event_count={pattern_event_count}, independently_corroborated={pattern_independently_corroborated_count}",
            ))
        else:
            defense.append(Finding(
                "self_corroborating_pattern",
                "Repeated events exist for this seat, but none of them had independent evidence — they only repeat each other.",
                f"event_count={pattern_event_count}, independently_corroborated=0",
                disqualifying=False,  # already excluded from prosecution above; shown for transparency, not a veto
            ))

    prosecution_clears_bar = (
        corroborated_by_duration or corroborated_by_object or gesture_active or corroborated_by_pattern
    )

    # --- Defense: specific measured counter-evidence ---
    # Accuracy audit (2026-08-22): this used to veto ANY alert whenever
    # fused pose confidence was low, including one resting entirely on a
    # confirmed object detection -- which has its own, separately-reported
    # confidence and does not depend on how well the pose model tracked
    # this person's skeleton. A candidate turned away from camera (their
    # actual posture, not a flaw) has low pose confidence by construction,
    # which was silently vetoing a genuinely confirmed phone detection
    # (found via ground-truth audit, data/test_videos/01). Pose confidence
    # only bears on pose-DERIVED evidence (sustained duration, gesture) --
    # it says nothing about whether the object detector's own judgment
    # should be trusted, so it only veto's here when no object corroborates.
    if fused_confidence < low_confidence_threshold and object_label is None:
        defense.append(Finding(
            "low_detection_confidence",
            "Pose/detection confidence for this reading was low.",
            f"fused_confidence={fused_confidence:.2f} (bar: {low_confidence_threshold:.2f})",
            disqualifying=True,
        ))
    if camera_needs_attention:
        defense.append(Finding(
            "camera_needs_attention",
            "This seat's camera currently has a poor seat-anchor hit rate.",
            "calibration_quality.status == needs_attention",
            disqualifying=True,
        ))
    if recent_false_alarm_count > 0:
        defense.append(Finding(
            "recent_false_positive_history",
            "This seat has had a recent alert dismissed as a false alarm.",
            f"false_alarm_dismissals_this_session={recent_false_alarm_count}",
            disqualifying=False,  # context for the invigilator, not a veto on its own
        ))
    # Accuracy audit (2026-08-22): this used to key off "is the detector
    # fine-tuned," which backwards-vetoed a genuinely reliable detection.
    # data/weights/phone_detector_v1.pt (the fine-tune) turned out to be
    # both class-mismatched (see backend/pipeline_worker.py's comment) and
    # documented as overfit on real footage; the stock COCO-pretrained
    # detector is what's actually in use, and its "cell phone" class is a
    # mature, heavily-validated COCO class -- confirmed directly against
    # real ground-truth footage (data/test_videos/01) to genuinely detect
    # a real phone. "book" (perception/object_detector.py's own
    # COCO_CONTRABAND_CLASSES comment) is explicitly an unvalidated
    # placeholder proxy for paper/chit, not a real target class, and stays
    # untrusted as sole evidence. object_class_verified reflects THIS
    # per-label distinction, not model training history.
    if corroborated_by_object and not object_class_verified and len(prosecution) == 1:
        defense.append(Finding(
            "unverified_object_class",
            f"This alert's only corroboration is a '{object_label}' detection, a class not yet validated as reliable evidence on its own.",
            "object_class_verified=False, and no other corroborating signal fired",
            disqualifying=True,
        ))
    if recent_calibration_warning:
        defense.append(Finding(
            "calibration_issue_signature",
            "This seat recently showed a hand-crossing calibration-issue signature, not a genuine incident.",
            "gesture_detector flagged likely_calibration_issue for this seat recently",
            disqualifying=True,
        ))

    disqualified = any(f.disqualifying for f in defense)
    is_alert = prosecution_clears_bar and not disqualified

    return AdjudicationResult(is_alert=is_alert, prosecution=prosecution, defense=defense)
