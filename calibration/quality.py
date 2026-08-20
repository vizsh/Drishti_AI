"""Live calibration-quality signal (Part 2.5 of the 2026-08-21 audit
follow-up).

The multi-video robustness test found that a rushed or rough seat
calibration doesn't fail loudly — it silently produces a low seat-anchor
hit rate (2/1,319 detections matched a seat, vs 826/1,319 for a properly
calibrated camera on the same footage) and, downstream, confident-looking
but spurious repeated gesture alerts (see behaviour/gestures.py's
repeat-detection addition). This module turns the same hit-rate metric used
manually during that audit into a live, per-camera signal the running
pipeline tracks on its own, so a bad calibration is visible instead of
silent.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class CalibrationQuality:
    camera_id: str
    hit_rate: Optional[float]  # None until min_samples reached
    sample_count: int
    status: str  # "gathering" | "good" | "needs_attention"


class SeatAnchorQualityTracker:
    """Rolling seat-anchor hit rate for one camera.

    A rolling window (not a lifetime average) so the signal reflects the
    camera's *current* calibration, not a first-few-minutes snapshot that
    stays stuck after a mid-session recalibration. window_size=500 at the
    system's ~10fps sampling is roughly the last 50s of detections — long
    enough to smooth over a single invigilator walking through frame
    (an expected, legitimate miss), short enough to react if a camera gets
    physically bumped mid-exam.
    """

    def __init__(
        self,
        camera_id: str,
        window_size: int = 500,
        min_samples: int = 100,
        low_confidence_threshold: float = 0.4,
    ):
        self.camera_id = camera_id
        self.min_samples = min_samples
        self.low_confidence_threshold = low_confidence_threshold
        self._outcomes: deque[bool] = deque(maxlen=window_size)

    def record(self, hit: bool) -> None:
        self._outcomes.append(hit)

    def snapshot(self) -> CalibrationQuality:
        n = len(self._outcomes)
        if n < self.min_samples:
            return CalibrationQuality(camera_id=self.camera_id, hit_rate=None, sample_count=n, status="gathering")
        rate = sum(self._outcomes) / n
        status = "needs_attention" if rate < self.low_confidence_threshold else "good"
        return CalibrationQuality(camera_id=self.camera_id, hit_rate=round(rate, 3), sample_count=n, status=status)
