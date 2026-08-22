"""Temporal persistence gate for object detections (accuracy audit,
2026-08-22).

Reproduced against real ground-truth footage (data/test_videos/01,
"Candidate was found using a mobile phone in the examination hall"): the
ROI-cropped object detector (perception/roi_contraband.py) genuinely
detects the real phone in this footage -- confidence peaks at 0.364 within
the actual real incident window -- but sits in a noisy 0.10-0.33 band for
most of it, well below the 0.30-0.35 single-frame confidence bar the
pipeline used to require before this fix. The real detection was being
thrown away by a threshold tuned for precision with no matching recall
check, not because the object genuinely isn't visible to the model.

Fix, following this project's own stated accuracy checklist ("temporal
smoothing... never classify on one frame") applied to object detection,
which previously had none: lower the per-frame confidence floor (so a real
but momentarily-weak reading isn't discarded outright) and require the
SAME label to be seen at least twice within a short window before it
counts as a confirmed detection for scoring/alerting.

Second finding, from the SAME audit pass, against a different real video
(data/test_videos/04): a static water bottle sitting on a desk was
misclassified as "cell phone" at low confidence (0.15-0.30) throughout the
ENTIRE 143s clip. A one-off false positive gets filtered by the repetition
requirement above -- but a persistently-misdetected STATIC object trivially
satisfies "seen twice," every time, forever, and (once object detection
was allowed to trigger its own alert independent of any motion event) that
turned a background object into a standing false alarm generator. The
actual distinguishing feature isn't confidence -- the false positive's
confidence band overlaps the real phone's -- it's that a genuinely held
object moves with the hand over time, while a desk fixture's detected
position barely shifts at all no matter how long it's tracked. This module
now also tracks each hit's image-plane position and refuses to confirm a
label whose recent positions are suspiciously static.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

Point2D = tuple[float, float]


@dataclass
class ConfirmedObject:
    label: str
    confidence: float  # peak confidence among the corroborating hits
    duration: float  # seconds between the first and most recent corroborating hit


class ObjectPersistenceTracker:
    def __init__(
        self,
        window_seconds: float = 3.0,
        min_hits: int = 2,
        static_check_window_seconds: float = 12.0,
        static_check_min_samples: int = 4,
        static_spread_px: float = 14.0,
    ):
        self.window_seconds = window_seconds
        self.min_hits = min_hits
        # A longer horizon than window_seconds on purpose: a static
        # object's position needs enough samples over enough real time to
        # confidently call "this hasn't moved," whereas window_seconds
        # only needs to catch a genuine object being seen twice quickly.
        self.static_check_window_seconds = static_check_window_seconds
        self.static_check_min_samples = static_check_min_samples
        self.static_spread_px = static_spread_px
        self._hits: dict[str, Deque[tuple[float, str, float]]] = {}
        self._positions: dict[tuple[str, str], Deque[tuple[float, float, float]]] = {}

    def observe(
        self,
        seat_id: str,
        timestamp: float,
        label: Optional[str],
        confidence: float,
        position: Optional[Point2D] = None,
    ) -> Optional[ConfirmedObject]:
        """Call once per frame per seat with that frame's raw (possibly
        None) object detection and its image-plane center (for the
        static-object check). Returns a ConfirmedObject once the SAME
        label has been seen >= min_hits times within window_seconds AND
        its recent positions aren't suspiciously static, else None."""
        history = self._hits.setdefault(seat_id, deque())
        cutoff = timestamp - self.window_seconds
        while history and history[0][0] < cutoff:
            history.popleft()
        if label is not None:
            history.append((timestamp, label, confidence))
            if position is not None:
                pos_key = (seat_id, label)
                positions = self._positions.setdefault(pos_key, deque())
                positions.append((timestamp, position[0], position[1]))
                static_cutoff = timestamp - self.static_check_window_seconds
                while positions and positions[0][0] < static_cutoff:
                    positions.popleft()

        if not history:
            return None
        current_label = history[-1][1]
        same_label = [(t, c) for (t, l, c) in history if l == current_label]
        if len(same_label) < self.min_hits:
            return None

        if self._is_static(seat_id, current_label):
            return None

        first_t = same_label[0][0]
        peak_conf = max(c for _, c in same_label)
        return ConfirmedObject(label=current_label, confidence=peak_conf, duration=timestamp - first_t)

    def _is_static(self, seat_id: str, label: str) -> bool:
        positions = self._positions.get((seat_id, label))
        if positions is None or len(positions) < self.static_check_min_samples:
            return False  # not enough samples yet to call it either way
        xs = [x for _, x, _ in positions]
        ys = [y for _, _, y in positions]
        spread = (max(xs) - min(xs)) + (max(ys) - min(ys))
        return spread < self.static_spread_px
