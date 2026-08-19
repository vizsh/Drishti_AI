"""Stage 2: multi-person tracking.

BoT-SORT, chosen over DeepSORT/ByteTrack/OC-SORT (docs/architecture.md §2):
camera-motion compensation absorbs fixed-mount vibration (HVAC/fans), and it
fits the 15-40 objects/camera density of a real exam hall better than
ByteTrack. Ships as Ultralytics' own default tracker, so it's driven through
YOLO's built-in `.track()` API rather than a separate library.

Tracking alone is not identity-stable across occlusion on its own — a
multi-second occlusion can still swap IDs. That's what calibration/'s
seat-anchoring homography (Stage 4) is for; this stage only handles
frame-to-frame association.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from ultralytics import YOLO

COCO_PERSON_CLASS_ID = 0


@dataclass
class TrackedDetection:
    track_id: int
    xyxy: tuple[float, float, float, float]
    confidence: float

    @property
    def foot_point(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)


class PersonTracker:
    def __init__(
        self,
        weights: str = "yolo11n.pt",
        confidence_threshold: float = 0.4,
        device: Optional[str] = None,
        tracker_config: str = "botsort.yaml",
    ):
        self.model = YOLO(weights)
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.tracker_config = tracker_config

    def track(self, image: np.ndarray) -> List[TrackedDetection]:
        """Call once per frame, in order, on the same instance — BoT-SORT
        keeps track state internally via persist=True."""
        results = self.model.track(
            image,
            classes=[COCO_PERSON_CLASS_ID],
            conf=self.confidence_threshold,
            device=self.device,
            tracker=self.tracker_config,
            persist=True,
            verbose=False,
        )
        tracked: List[TrackedDetection] = []
        boxes = results[0].boxes
        if boxes.id is None:
            return tracked  # no confirmed tracks yet this frame
        for box, track_id in zip(boxes, boxes.id):
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            tracked.append(
                TrackedDetection(track_id=int(track_id), xyxy=(x1, y1, x2, y2), confidence=conf)
            )
        return tracked

    def reset(self) -> None:
        """Clear track state — call between independent videos/streams."""
        if hasattr(self.model.predictor, "trackers"):
            self.model.predictor.trackers[0].reset()
