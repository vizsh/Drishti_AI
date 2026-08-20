"""Session-wide motion heatmap.

This is PS #2's "motion heatmaps" objective, but deliberately NOT built as
a separate offline pipeline re-processing the same footage — it's computed
as a free byproduct of frames the live PS #1 pipeline (backend/
pipeline_worker.py) already decodes every frame. Serves PS #1 directly:
after an exam, an invigilator gets one image showing where activity
concentrated in the room over the whole session — exactly PS #2's
requested signal, without a second processing pass.

Frame-to-frame differencing — PS #2's own named technique ("frame-to-frame
motion estimation techniques") — rather than MOG2 background subtraction:
this accumulates an aggregate visualization, not per-frame event
detection, so MOG2's extra sophistication isn't needed here.
"""

from __future__ import annotations

import cv2
import numpy as np


class MotionHeatmapAccumulator:
    def __init__(self, frame_shape: tuple[int, int]):
        """frame_shape: (height, width) of the frames that will be fed in."""
        h, w = frame_shape
        self._accum = np.zeros((h, w), dtype=np.float32)
        self._prev_gray: np.ndarray | None = None
        self.frame_count = 0

    def update(self, image: np.ndarray) -> None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self._prev_gray is not None:
            diff = cv2.absdiff(gray, self._prev_gray)
            _, motion_mask = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
            self._accum += motion_mask.astype(np.float32)
            self.frame_count += 1
        self._prev_gray = gray

    def render(self, base_image: np.ndarray | None = None, alpha: float = 0.55) -> np.ndarray:
        """Colorized heatmap, optionally overlaid on base_image (e.g. a
        representative frame of the room) so seats/desks stay recognizable
        under the overlay rather than a heatmap floating in a void."""
        positive = self._accum[self._accum > 0]
        if positive.size == 0:
            normalized = self._accum.astype(np.uint8)
        else:
            # 95th percentile, not the max, as the normalization ceiling —
            # a handful of extreme-motion pixels (e.g. a door opening once)
            # would otherwise wash out the rest of the session's signal.
            ceiling = np.percentile(positive, 95) + 1e-6
            normalized = np.clip(self._accum / ceiling * 255, 0, 255).astype(np.uint8)
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
        if base_image is None:
            return colored
        base = cv2.resize(base_image, (colored.shape[1], colored.shape[0]))
        return cv2.addWeighted(colored, alpha, base, 1 - alpha, 0)
