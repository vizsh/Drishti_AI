"""Stage 8: named-gesture detectors for the PS's explicitly called-out
behaviours — "unusual hand movements... attempts to communicate
non-verbally" and "body rotation toward neighbouring students" (PS #1 text).
The generic torso-yaw/motion z-scores (Stages 6-7) only weakly capture these
as *specific* named behaviours; this module gives them concrete, geometric
meaning by reusing the seat-anchoring homography already built (Stage 3).

ST-GCN++ (PYSKL), the ML classifier docs/architecture.md §6 specifies, is
NOT implemented here — it needs labeled exam-specific gesture clips, which
don't exist yet. This is the rule-based signal the architecture doc says
must run in parallel with it regardless (§6: "hybrid... rule-based
thresholds as a second signal that runs in parallel"), so it's not a
placeholder — it stands on its own and stays in the fused system once
ST-GCN++ is added. See docs/build_order.md for the ST-GCN++ status.

Deliberately does NOT include a "sustained lean/turn" flat-threshold
detector — an early version did, and testing it against real footage
(run_stage8_demo.py) caught it re-introducing the exact failure mode Stage
6 exists to eliminate: a fixed magnitude threshold fires constantly on a
seat whose camera angle alone gives it a naturally offset torso_yaw
baseline, regardless of real behaviour. Stage 7's z-score deviation event
on the torso_yaw signal already covers "sustained lean/turn" correctly
(baseline-relative, validated) — duplicating it here as an unrelated flat
threshold would just reintroduce noise. hand_reach_across is the only
detector below because it's geometrically grounded (crossing into a
neighbor's seat zone) rather than threshold-tuned, so it doesn't have that
problem.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from calibration.homography import SeatCalibration
from perception.pose import KEYPOINT_NAMES, PoseResult

LEFT_WRIST = KEYPOINT_NAMES.index("left_wrist")
RIGHT_WRIST = KEYPOINT_NAMES.index("right_wrist")

# Accuracy hardening (2026-08-23, found live testing new real footage): no
# genuine single hand-reach across a desk boundary plausibly lasts longer
# than this — a "reach" that stays continuously active for tens of seconds
# means a wrist keypoint is persistently resolving to the wrong seat
# (imprecise/eyeballed calibration, lens distortion, overlapping snap
# zones), not a real sustained gesture. A real camera produced exactly
# this: a 92-second "hand_reach_across" event from calibration estimated
# by eye rather than measured with calibrate_tool.py. Treated as a
# likely_calibration_issue rather than a genuine incident, same as the
# existing same-direction-repeat signature -- this is the SAME kind of
# "this pattern means something is miscalibrated, not that a real
# incident is happening" signal, not a new detection mechanism.
MAX_PLAUSIBLE_REACH_SECONDS = 15.0


def nearest_neighbor_seat(seat_cal: SeatCalibration, seat_id: str) -> Optional[str]:
    """The closest other calibrated seat, by plane distance — gives "toward
    a neighbour" a concrete geometric meaning instead of a vague direction."""
    if seat_id not in seat_cal.seats:
        return None
    own = seat_cal.seats[seat_id]
    best, best_dist = None, float("inf")
    for other_id, pos in seat_cal.seats.items():
        if other_id == seat_id:
            continue
        dist = math.hypot(pos[0] - own[0], pos[1] - own[1])
        if dist < best_dist:
            best_dist = dist
            best = other_id
    return best


@dataclass
class GestureEvent:
    seat_id: str
    gesture: str  # "hand_reach_across"
    start_time: float
    end_time: float
    neighbor_seat: Optional[str]
    # Part 2.5 (2026-08-21 audit follow-up): set when this event is the 4th+
    # hand_reach_across for the same (seat_id -> neighbor_seat) direction
    # within repeat_window_seconds. Found via the multi-video robustness
    # test: a roughly-calibrated camera produced 12 same-direction
    # hand_reach_across events for one seat pair over 79s of footage — a
    # signature of overlapping seat zones (see the NOTE in
    # GestureDetector.observe below), not 12 genuine incidents.
    likely_calibration_issue: bool = False
    repeat_count: int = 0
    repeat_window_seconds: float = 0.0
    # Set-aware neighbor weighting (2026-08-23): a real anti-cheating
    # practice already used by institutions is issuing alternating
    # question-paper sets so adjacent students can't usefully copy off
    # each other. A hand-reach toward a neighbor on the SAME set is
    # meaningfully more suspicious than toward a different-set neighbor
    # (copying only helps if the answers are comparable) — this makes an
    # existing signal smarter with real domain context, not a new
    # detection mechanism. None when the seating chart doesn't carry
    # question-set data for these two seats (institution doesn't use the
    # practice, or hasn't uploaded a chart) — never fabricated.
    same_set_neighbor: Optional[bool] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class SustainedBooleanDetector:
    """Same sustained-duration filter as risk_engine.events'
    SustainedDeviationDetector, generalized to a boolean condition instead
    of a z-score crossing — never fire on a single-frame flicker."""

    def __init__(self, min_duration_seconds: float = 1.0):
        self.min_duration_seconds = min_duration_seconds
        self._active: dict[tuple[str, str], float] = {}

    def observe(self, key: tuple[str, str], timestamp: float, condition: bool) -> Optional[float]:
        """Returns the event's start_time if it just ended and held long
        enough, else None."""
        if condition:
            self._active.setdefault(key, timestamp)
            return None
        if key in self._active:
            start = self._active.pop(key)
            if timestamp - start >= self.min_duration_seconds:
                return start
        return None


class GestureDetector:
    def __init__(
        self,
        seat_cal: SeatCalibration,
        min_duration_seconds: float = 1.0,
        min_wrist_confidence: float = 0.35,
        repeat_window_seconds: float = 90.0,
        repeat_threshold: int = 3,
    ):
        self.seat_cal = seat_cal
        self.min_wrist_confidence = min_wrist_confidence
        self._hand_detector = SustainedBooleanDetector(min_duration_seconds)
        # Part 2.5: recent hand_reach_across timestamps per (seat_id,
        # neighbor_seat) *direction* — repeat_threshold prior events within
        # repeat_window_seconds flags the next one as a likely calibration
        # issue rather than a fresh genuine incident.
        self.repeat_window_seconds = repeat_window_seconds
        self.repeat_threshold = repeat_threshold
        self._recent_events: dict[tuple[str, str], deque[float]] = {}
        # Set-aware neighbor weighting: seat_id -> question-set label,
        # live-settable from the uploaded seating chart (see
        # PipelineWorker.set_seat_question_sets). Empty until a chart with
        # question-set data is actually uploaded — same_set_neighbor stays
        # None (not False) for any seat missing from this map, so "we
        # don't know" is never confused with "confirmed different sets."
        self.seat_question_sets: dict[str, str] = {}

    def set_question_sets(self, mapping: dict[str, str]) -> None:
        self.seat_question_sets = mapping

    def observe(self, seat_id: str, pose: PoseResult, timestamp: float) -> list[GestureEvent]:
        events: list[GestureEvent] = []
        neighbor = nearest_neighbor_seat(self.seat_cal, seat_id)
        if neighbor is None:
            return events

        keypoints = pose.smoothed_keypoints or pose.keypoints
        conf = pose.keypoint_confidence

        # Hand-reach: a wrist's projected position lands in a *different*
        # seat's zone than its owner's — geometrically grounded via the same
        # homography validated in Stage 3, not a heuristic angle guess.
        # NOTE: with the illustrative demo calibration, snap zones (radius
        # 60 plane units) overlap between adjacent seats spaced ~90 units
        # apart, so a real deployment needs calibrate_tool.py's actual
        # measured seat positions with non-overlapping zones before this
        # signal is trustworthy — same caveat as Stage 3/4's illustrative-
        # calibration findings.
        reaching = False
        for wrist_idx in (LEFT_WRIST, RIGHT_WRIST):
            if conf[wrist_idx] < self.min_wrist_confidence:
                continue
            wrist_seat, _ = self.seat_cal.nearest_seat(keypoints[wrist_idx])
            if wrist_seat is not None and wrist_seat != seat_id:
                reaching = True
                break

        start = self._hand_detector.observe(("hand", seat_id), timestamp, reaching)
        if start is not None:
            key = (seat_id, neighbor)
            history = self._recent_events.setdefault(key, deque())
            cutoff = timestamp - self.repeat_window_seconds
            while history and history[0] < cutoff:
                history.popleft()
            recent_count = len(history)
            history.append(timestamp)

            own_set = self.seat_question_sets.get(seat_id)
            neighbor_set = self.seat_question_sets.get(neighbor)
            same_set = (own_set == neighbor_set) if (own_set is not None and neighbor_set is not None) else None
            implausibly_long = (timestamp - start) > MAX_PLAUSIBLE_REACH_SECONDS

            events.append(
                GestureEvent(
                    seat_id=seat_id,
                    gesture="hand_reach_across",
                    start_time=start,
                    end_time=timestamp,
                    neighbor_seat=neighbor,
                    likely_calibration_issue=recent_count >= self.repeat_threshold or implausibly_long,
                    repeat_count=recent_count + 1,
                    repeat_window_seconds=self.repeat_window_seconds,
                    same_set_neighbor=same_set,
                )
            )
        return events


def explain_gesture(event: GestureEvent) -> str:
    """Deterministic template explanation, matching risk_engine/explain.py's
    style (docs/architecture.md §10) — measured facts only, no generative text."""
    base = f"Hand crossed into {event.neighbor_seat}'s desk space for {event.duration:.1f}s (from {event.seat_id})."
    if event.same_set_neighbor is True:
        return base + " Both seats are on the same question-paper set."
    return base


def explain_calibration_warning(event: GestureEvent) -> str:
    """Part 2.5: template explanation for the calibration-issue signal —
    same measured-fact style, naming the count/window so it's clear this is
    a pattern detection, not a single incident."""
    return (
        f"Possible calibration issue at {event.seat_id}: hand-crossing into {event.neighbor_seat}'s zone "
        f"detected {event.repeat_count} times in the last {event.repeat_window_seconds:.0f}s — recommend "
        f"recalibrating this camera rather than treating these as individual incidents."
    )
