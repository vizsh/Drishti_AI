"""One-Euro filter (Casiez et al., 2012) for keypoint smoothing.

docs/architecture.md §2: downstream angle/duration thresholds in the risk
engine will fire on raw per-frame keypoint jitter otherwise — a cheap,
high-value addition most teams skip. Adaptive: smooths more when a keypoint
is nearly still (killing jitter), less when it's moving fast (avoiding lag).
"""

from __future__ import annotations

import math
from typing import Optional


class _LowPassFilter:
    def __init__(self) -> None:
        self._value: Optional[float] = None

    def filter(self, value: float, alpha: float) -> float:
        if self._value is None:
            self._value = value
        else:
            self._value = alpha * value + (1.0 - alpha) * self._value
        return self._value


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_filter = _LowPassFilter()
        self._dx_filter = _LowPassFilter()
        self._last_time: Optional[float] = None
        self._last_x: Optional[float] = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: float) -> float:
        if self._last_time is None:
            dt = 1.0 / 30.0  # first sample: assume a reasonable default rate
        else:
            dt = max(timestamp - self._last_time, 1e-6)
        self._last_time = timestamp

        dx = 0.0 if self._last_x is None else (x - self._last_x) / dt
        self._last_x = x

        dx_hat = self._dx_filter.filter(dx, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        return self._x_filter.filter(x, self._alpha(cutoff, dt))


class KeypointSmoother:
    """Smooths a fixed-size set of (x, y) keypoints per tracked identity.

    One OneEuroFilter pair per (track_id, keypoint_index, axis) — created
    lazily on first sight. Call `reset(track_id)` when a track is lost long
    enough that resuming smoothing from stale state would do more harm than
    starting fresh (e.g. after a multi-second occlusion).
    """

    def __init__(self, num_keypoints: int = 17, min_cutoff: float = 1.0, beta: float = 0.02):
        self.num_keypoints = num_keypoints
        self.min_cutoff = min_cutoff
        self.beta = beta
        self._filters: dict[int, list[tuple[OneEuroFilter, OneEuroFilter]]] = {}

    def _filters_for(self, track_id: int) -> list[tuple[OneEuroFilter, OneEuroFilter]]:
        if track_id not in self._filters:
            self._filters[track_id] = [
                (OneEuroFilter(self.min_cutoff, self.beta), OneEuroFilter(self.min_cutoff, self.beta))
                for _ in range(self.num_keypoints)
            ]
        return self._filters[track_id]

    def smooth(self, track_id: int, keypoints: list[tuple[float, float]], timestamp: float) -> list[tuple[float, float]]:
        filters = self._filters_for(track_id)
        smoothed = []
        for (x, y), (fx, fy) in zip(keypoints, filters):
            smoothed.append((fx.filter(x, timestamp), fy.filter(y, timestamp)))
        return smoothed

    def reset(self, track_id: int) -> None:
        self._filters.pop(track_id, None)
