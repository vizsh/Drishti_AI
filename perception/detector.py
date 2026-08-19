"""Stage 1: person detection.

YOLO11n, COCO-pretrained, person class only (docs/architecture.md §2). No
fine-tuning needed at this stage — chosen over RTMDet-tiny/Faster-RCNN for
deployment tooling maturity (direct TensorRT export for the Jetson target).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
from ultralytics import YOLO

COCO_PERSON_CLASS_ID = 0


@dataclass
class Detection:
    xyxy: tuple[float, float, float, float]
    confidence: float

    @property
    def foot_point(self) -> tuple[float, float]:
        """Bottom-center of the box — used by calibration/ for homography seat-anchoring."""
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)


class PersonDetector:
    def __init__(self, weights: str = "yolo11n.pt", confidence_threshold: float = 0.4, device: str | None = None):
        self.model = YOLO(weights)
        self.confidence_threshold = confidence_threshold
        self.device = device

    def detect(self, image: np.ndarray) -> List[Detection]:
        results = self.model.predict(
            image,
            classes=[COCO_PERSON_CLASS_ID],
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        detections: List[Detection] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append(Detection(xyxy=(x1, y1, x2, y2), confidence=conf))
        return detections
