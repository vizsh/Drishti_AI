"""Lighting robustness (docs/architecture.md §8, PS risk row "Poor Lighting
Conditions" / Technology Challenge #4: "low lighting, shadows, glare").

CLAHE (Contrast Limited Adaptive Histogram Equalization) applied only when
a frame's mean brightness falls below a threshold — cheap (a few ms) and,
per the architecture doc's own research, the strongest real-time-compatible
method among lighting-enhancement techniques. Conditional rather than
always-on: CLAHE has a real cost and a well-lit frame doesn't need it.
"""

from __future__ import annotations

import cv2
import numpy as np


def mean_brightness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def apply_clahe(image: np.ndarray, clip_limit: float = 2.5, tile_grid_size: tuple[int, int] = (8, 8)) -> np.ndarray:
    """CLAHE on the L channel of LAB color space — enhances local contrast
    without washing out color balance the way a naive global histogram
    equalization on a BGR/gray image would."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    l_enhanced = clahe.apply(l)
    enhanced = cv2.merge([l_enhanced, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def enhance_if_dark(image: np.ndarray, brightness_threshold: float = 90.0) -> tuple[np.ndarray, bool]:
    """Returns (possibly-enhanced image, was_enhanced) — callers can log or
    surface when enhancement kicked in rather than it happening silently."""
    if mean_brightness(image) < brightness_threshold:
        return apply_clahe(image), True
    return image, False
