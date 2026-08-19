"""Stage 6: per-seat temporal buffer + baseline calibration
(docs/architecture.md §5) — the single highest-leverage fix for false
positives (PS risk #1). Score behaviour as deviation from *that student's
own* settling-window baseline, never a flat threshold: a naturally fidgety
student and a still one shouldn't share one cutoff.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import numpy as np


def compute_motion_magnitude(
    prev_keypoints: list[tuple[float, float]],
    curr_keypoints: list[tuple[float, float]],
    keypoint_confidence: list[float],
    shoulder_width: float,
    min_conf: float = 0.3,
) -> float:
    """Mean per-keypoint displacement between two frames, normalized by
    shoulder width so a person far from camera (few pixels of real movement)
    is comparable to one close up (many pixels for the same real movement).
    Returns 0.0 if too few confident keypoints are available to measure.
    """
    if shoulder_width <= 1e-3:
        return 0.0
    displacements = []
    for (px, py), (cx, cy), conf in zip(prev_keypoints, curr_keypoints, keypoint_confidence):
        if conf >= min_conf:
            displacements.append(float(np.hypot(cx - px, cy - py)))
    if not displacements:
        return 0.0
    return float(np.mean(displacements)) / shoulder_width


@dataclass
class TemporalSample:
    timestamp: float
    torso_yaw: Optional[float]  # from PoseResult.torso_yaw_proxy(), None if unreliable
    motion_magnitude: float


class SeatTemporalBuffer:
    """Rolling window of recent samples for one seat (docs/architecture.md
    §5: ~5-10 second buffer feeding both baseline stats and downstream
    behaviour scoring)."""

    def __init__(self, window_seconds: float = 10.0):
        self.window_seconds = window_seconds
        self.samples: Deque[TemporalSample] = deque()

    def add(self, sample: TemporalSample) -> None:
        self.samples.append(sample)
        cutoff = sample.timestamp - self.window_seconds
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def torso_yaw_values(self) -> list[float]:
        return [s.torso_yaw for s in self.samples if s.torso_yaw is not None]

    def motion_magnitudes(self) -> list[float]:
        return [s.motion_magnitude for s in self.samples]


@dataclass
class SeatBaseline:
    torso_yaw_mean: float
    torso_yaw_std: float
    motion_mean: float
    motion_std: float
    min_std: float = 1e-3  # floor so a perfectly still calibration window doesn't divide by zero

    def yaw_zscore(self, value: float) -> float:
        return (value - self.torso_yaw_mean) / max(self.torso_yaw_std, self.min_std)

    def motion_zscore(self, value: float) -> float:
        return (value - self.motion_mean) / max(self.motion_std, self.min_std)


class BaselineCalibrator:
    """Manages the settling-window calibration for every seat.

    docs/architecture.md §5: the first 2-3 minutes of the exam (paper
    distribution, instructions) is the settling window. Until it completes
    for a seat, that seat has no baseline and risk scoring must fall back —
    never fabricate a z-score against an incomplete baseline.
    """

    def __init__(self, settling_window_seconds: float = 150.0):
        self.settling_window_seconds = settling_window_seconds
        self._start_time: dict[str, float] = {}
        self._calibration_samples: dict[str, list[TemporalSample]] = {}
        self._baselines: dict[str, SeatBaseline] = {}

    def is_calibrated(self, seat_id: str) -> bool:
        return seat_id in self._baselines

    def baseline(self, seat_id: str) -> Optional[SeatBaseline]:
        return self._baselines.get(seat_id)

    def observe(self, seat_id: str, sample: TemporalSample) -> None:
        """Feed a sample during the settling window. No-op once calibrated."""
        if seat_id in self._baselines:
            return
        if seat_id not in self._start_time:
            self._start_time[seat_id] = sample.timestamp
            self._calibration_samples[seat_id] = []
        self._calibration_samples[seat_id].append(sample)

        elapsed = sample.timestamp - self._start_time[seat_id]
        if elapsed >= self.settling_window_seconds:
            self._finalize(seat_id)

    def _finalize(self, seat_id: str) -> None:
        samples = self._calibration_samples.pop(seat_id)
        yaw_values = [s.torso_yaw for s in samples if s.torso_yaw is not None]
        motion_values = [s.motion_magnitude for s in samples]

        self._baselines[seat_id] = SeatBaseline(
            torso_yaw_mean=float(np.mean(yaw_values)) if yaw_values else 0.0,
            torso_yaw_std=float(np.std(yaw_values)) if yaw_values else 0.0,
            motion_mean=float(np.mean(motion_values)) if motion_values else 0.0,
            motion_std=float(np.std(motion_values)) if motion_values else 0.0,
        )

    def calibration_progress(self, seat_id: str, now: float) -> float:
        """0.0-1.0 fraction of the settling window elapsed for this seat."""
        if seat_id in self._baselines:
            return 1.0
        if seat_id not in self._start_time:
            return 0.0
        return min(1.0, (now - self._start_time[seat_id]) / self.settling_window_seconds)

    def widen_threshold(self, seat_id: str, factor: float = 1.15) -> None:
        """docs/architecture.md §10 feedback loop: an invigilator dismissing
        an alert as a false positive widens that seat's tolerance live,
        without waiting for a full recalibration."""
        baseline = self._baselines.get(seat_id)
        if baseline is None:
            return
        baseline.torso_yaw_std *= factor
        baseline.motion_std *= factor
