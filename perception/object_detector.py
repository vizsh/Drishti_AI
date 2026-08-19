"""Stage 4: contraband object detection (phone / paper / earpiece).

docs/architecture.md §4: no pretrained model ships an "exam contraband"
detector — paper_chit and earpiece genuinely need custom fine-tuning on a
merged public + own-staged dataset (Roboflow/Kaggle + own footage).

Phone is the one exception worth exploiting first: COCO's own 80 classes
already include "cell phone" (class 67), so YOLO11n's stock pretrained
weights detect phones with zero fine-tuning. This module runs that as a
free baseline signal (validate against real footage before assuming it's
good enough for production thresholds) and is the extension point where
fine-tuned weights get swapped in once a custom dataset exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from ultralytics import YOLO

# COCO class indices for objects also relevant to exam-hall contraband.
# "book" is the closest COCO proxy for a paper/chit — not accurate, listed
# only as a placeholder until a fine-tuned paper_chit class exists.
COCO_CONTRABAND_CLASSES = {
    67: "cell phone",
    73: "book",  # placeholder proxy for paper_chit — NOT validated, see docstring
}


@dataclass
class ObjectDetection:
    label: str
    xyxy: tuple[float, float, float, float]
    confidence: float


class ObjectDetector:
    """Baseline: stock COCO-pretrained YOLO11n, phone/book classes only.

    Swap `weights` to a fine-tuned checkpoint (trained per docs/architecture.md
    §4 dataset strategy) once one exists, and extend the class list to include
    paper_chit/earpiece trained specifically for this project.
    """

    def __init__(
        self,
        weights: str = "yolo11n.pt",
        classes: Optional[dict[int, str]] = None,
        confidence_threshold: float = 0.3,
        device: Optional[str] = None,
    ):
        self.model = YOLO(weights)
        self.classes = classes or COCO_CONTRABAND_CLASSES
        self.confidence_threshold = confidence_threshold
        self.device = device

    def detect(self, image: np.ndarray) -> List[ObjectDetection]:
        results = self.model.predict(
            image,
            classes=list(self.classes.keys()),
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        detections: List[ObjectDetection] = []
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            detections.append(
                ObjectDetection(label=self.classes.get(cls_id, str(cls_id)), xyxy=(x1, y1, x2, y2), confidence=conf)
            )
        return detections
