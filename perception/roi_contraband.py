"""Stage 4 accuracy pass (Phase 2b, 2026-08-21): ROI-based contraband
detection.

Running the object detector on the full downsampled frame gives it a large
share of static background (desks, chairs, walls) at tiny relative
resolution. docs/build_order.md records phone_detector_v1 "false-positived
on a chair" on real footage - reproduced this session (300/300 frames of
video 04 fired a "cell phone" detection locked onto the same static
bounding box, clearly furniture, not a hand-held object). This crops a
per-student workspace region from pose keypoints (shoulders/elbows/wrists)
before running the detector, so it only ever looks at the area a hand-held
object could actually appear in - not just a performance optimization, a
plausible fix for the actual overfitting behavior, since the model never
sees the static background that was triggering it.
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from perception.object_detector import ObjectDetection, ObjectDetector
from perception.pose import PoseResult

LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
_ROI_KEYPOINT_IDXS = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW, LEFT_WRIST, RIGHT_WRIST)
_MIN_KP_CONF = 0.3
_PAD_RATIO = 0.35  # expand past the keypoint bbox to include the desk surface in front of the student


def workspace_roi(pose: PoseResult, image_width: int, image_height: int) -> Optional[tuple[int, int, int, int]]:
    """Bounding box around a student's shoulders/elbows/wrists, padded to
    include the desk surface in front of them — the region a hand-held
    object would actually appear in, not the whole frame. None if too few
    of those keypoints are confident enough to trust."""
    keypoints = pose.smoothed_keypoints or pose.keypoints
    pts = [keypoints[i] for i in _ROI_KEYPOINT_IDXS if pose.keypoint_confidence[i] >= _MIN_KP_CONF]
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    w, h = (x2 - x1), (y2 - y1)
    pad_x = w * _PAD_RATIO + 20
    pad_y_top = h * _PAD_RATIO + 20
    pad_y_bottom = h * _PAD_RATIO * 1.5 + 30  # extra downward — toward the desk, where hands rest
    rx1 = max(0, int(x1 - pad_x))
    ry1 = max(0, int(y1 - pad_y_top))
    rx2 = min(image_width, int(x2 + pad_x))
    ry2 = min(image_height, int(y2 + pad_y_bottom))
    if rx2 <= rx1 or ry2 <= ry1:
        return None
    return (rx1, ry1, rx2, ry2)


def detect_in_roi(
    detector: ObjectDetector, image: np.ndarray, roi: tuple[int, int, int, int], upscale: float = 2.0
) -> list[ObjectDetection]:
    """Crops the ROI, upscales it (more relative pixels for the detector
    than the full downsampled frame gave it), runs detection, then maps
    boxes back to full-frame coordinates so callers don't need to know
    detection ran on a crop."""
    x1, y1, x2, y2 = roi
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    h, w = crop.shape[:2]
    resized = cv2.resize(crop, (max(1, int(w * upscale)), max(1, int(h * upscale))))
    detections = detector.detect(resized)
    out: list[ObjectDetection] = []
    for d in detections:
        dx1, dy1, dx2, dy2 = d.xyxy
        out.append(
            ObjectDetection(
                label=d.label,
                xyxy=(x1 + dx1 / upscale, y1 + dy1 / upscale, x1 + dx2 / upscale, y1 + dy2 / upscale),
                confidence=d.confidence,
            )
        )
    return out
