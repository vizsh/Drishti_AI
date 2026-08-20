"""Multi-camera confidence fusion (docs/architecture.md §8: "when two
cameras cover the same seat, fuse their pose/object detections with
confidence weighting... instead of treating cameras independently") — PS
risk row "Occlusion": if one camera's view of a seat is blocked (a
neighbor leaning across it), a second camera's clear view should carry
that seat instead of the system losing the student for those frames.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SeatObservation:
    """One camera's reading of one seat for one frame — the fusion input."""

    camera_id: str
    torso_yaw: Optional[float]
    motion_magnitude: float
    pose_confidence: float  # PoseResult.detection_confidence()
    object_label: Optional[str] = None
    object_confidence: float = 0.0


def fuse_seat_observations(observations: list[SeatObservation]) -> SeatObservation:
    """Combines same-seat readings from multiple cameras in one frame.

    - torso_yaw / motion_magnitude: confidence-weighted average — a camera
      whose view of this seat is occluded (low pose_confidence) contributes
      proportionally less than one with a clear view, rather than the two
      views counting equally regardless of reliability.
    - object detection: logical OR, keeping the higher-confidence hit — a
      phone hidden from one angle may still be visible from another, so a
      miss on one camera must never suppress a hit on another.
    - pose_confidence of the fused result: the MAX across cameras, not an
      average. This is the point of occlusion fusion: if camera A is fully
      blocked (confidence ~0) but camera B has a clear view (confidence
      0.9), the seat's fused coverage is 0.9, not ~0.45 — averaging would
      understate how well-covered the seat actually is when at least one
      camera can see it clearly.

    A single observation (the common single-camera case, e.g. this
    project's own demo) passes through unchanged — fusion must never alter
    already-validated single-camera behaviour from Stages 1-9.
    """
    if not observations:
        raise ValueError("fuse_seat_observations requires at least one observation")
    if len(observations) == 1:
        return observations[0]

    def weighted_average(attr: str) -> Optional[float]:
        pairs = [(getattr(o, attr), o.pose_confidence) for o in observations if getattr(o, attr) is not None]
        weight_sum = sum(w for _, w in pairs)
        if not pairs or weight_sum <= 1e-9:
            return None
        return sum(v * w for v, w in pairs) / weight_sum

    fused_yaw = weighted_average("torso_yaw")
    fused_motion = weighted_average("motion_magnitude") or 0.0

    object_label: Optional[str] = None
    object_confidence = 0.0
    for o in observations:
        if o.object_label and o.object_confidence > object_confidence:
            object_label = o.object_label
            object_confidence = o.object_confidence

    return SeatObservation(
        camera_id=",".join(o.camera_id for o in observations),
        torso_yaw=fused_yaw,
        motion_magnitude=fused_motion,
        pose_confidence=max(o.pose_confidence for o in observations),
        object_label=object_label,
        object_confidence=object_confidence,
    )
