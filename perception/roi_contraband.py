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


def _crop_and_resize(image: np.ndarray, roi: tuple[int, int, int, int], upscale: float) -> Optional[np.ndarray]:
    x1, y1, x2, y2 = roi
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    h, w = crop.shape[:2]
    return cv2.resize(crop, (max(1, int(w * upscale)), max(1, int(h * upscale))))


def _remap_to_full_frame(
    detections: list[ObjectDetection], roi: tuple[int, int, int, int], upscale: float
) -> list[ObjectDetection]:
    x1, y1, _, _ = roi
    return [
        ObjectDetection(
            label=d.label,
            xyxy=(
                x1 + d.xyxy[0] / upscale,
                y1 + d.xyxy[1] / upscale,
                x1 + d.xyxy[2] / upscale,
                y1 + d.xyxy[3] / upscale,
            ),
            confidence=d.confidence,
        )
        for d in detections
    ]


def detect_in_roi(
    detector: ObjectDetector, image: np.ndarray, roi: tuple[int, int, int, int], upscale: float = 2.0
) -> list[ObjectDetection]:
    """Crops the ROI, upscales it (more relative pixels for the detector
    than the full downsampled frame gave it), runs detection, then maps
    boxes back to full-frame coordinates so callers don't need to know
    detection ran on a crop."""
    resized = _crop_and_resize(image, roi, upscale)
    if resized is None:
        return []
    return _remap_to_full_frame(detector.detect(resized), roi, upscale)


def detect_in_rois_batched(
    detector: ObjectDetector,
    image: np.ndarray,
    rois: list[tuple[int, int, int, int]],
    upscale: float = 2.0,
) -> list[list[ObjectDetection]]:
    """Latency pass (2026-08-22): when multiple seats are due for an
    object-detect check in the same frame, this replaces N sequential
    detect_in_roi() calls (N Python calls + N CUDA kernel launches for the
    identical model) with one batched forward pass over all N crops —
    ObjectDetector.detect_batch(). Same crop/upscale/remap math as
    detect_in_roi per seat, just issued together. Returns one detection
    list per input roi, in the same order (an empty-crop roi still gets an
    empty list at its index) — deliberately NOT keyed by seat_id, since two
    ROIs could in principle resolve to the same seat (e.g. a transient
    tracker glitch) and a dict would silently drop one."""
    crops: list[Optional[np.ndarray]] = [_crop_and_resize(image, roi, upscale) for roi in rois]
    valid_idxs = [i for i, c in enumerate(crops) if c is not None]
    if not valid_idxs:
        return [[] for _ in rois]
    batched = detector.detect_batch([crops[i] for i in valid_idxs])  # type: ignore[list-item]
    out: list[list[ObjectDetection]] = [[] for _ in rois]
    for i, dets in zip(valid_idxs, batched):
        out[i] = _remap_to_full_frame(dets, rois[i], upscale)
    return out
