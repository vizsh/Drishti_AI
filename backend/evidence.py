"""Evidence clip capture for confirmed alerts (docs/architecture.md §9, §11):
face-blurred clips are the only raw-video artifact the privacy design
allows to leave the edge boundary. Stored locally under data/evidence/ as
a MinIO stand-in — same substitution pattern as backend/db.py's
Postgres->SQLite (no MinIO server in this dev environment); swap the
storage backend later without changing the calling shape.

Face blurring uses pose keypoints (nose/eyes/ears, or a shoulder-relative
fallback), not a dedicated face detector. Tried cv2.CascadeClassifier
first and found this OpenCV 5.0 build removed it from the main module
entirely (no bundled Haar cascade XML files); cv2.FaceDetectorYN exists but
needs an external ONNX model this environment doesn't have. Deriving a head
box from pose keypoints avoids adding either dependency, reuses the
already-validated Stage 5 pose pipeline, and blurs *every* visible face in
frame (not just the alerting seat's) — genuine privacy compliance, not a
partial one.

Clips are stored as a numbered JPEG sequence + manifest.json, not an mp4.
Tried cv2.VideoWriter first (mp4v/avc1/H264/X264) and found this OpenCV
build has no working H.264 encoder (openh264 DLL missing) — mp4v is the
only fourcc that actually opens, and Chrome's <video> tag doesn't play
MPEG-4 Part 2. Rather than ship an evidence clip that silently fails to
play, this uses a format that's verifiably correct: a JPEG sequence the
dashboard plays back client-side at the original fps (backend/main.py
serves the folder statically; frontend cycles frames from manifest.json).
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Deque, Optional, Tuple

import cv2
import numpy as np

from perception.pose import KEYPOINT_NAMES, PoseResult

EVIDENCE_DIR = Path("data/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

_HEAD_KEYPOINT_IDXS = [KEYPOINT_NAMES.index(n) for n in ("nose", "left_eye", "right_eye", "left_ear", "right_ear")]
_LEFT_SHOULDER = KEYPOINT_NAMES.index("left_shoulder")
_RIGHT_SHOULDER = KEYPOINT_NAMES.index("right_shoulder")
_MIN_KEYPOINT_CONF = 0.3


def estimate_head_bbox(pose: PoseResult) -> Optional[tuple[int, int, int, int]]:
    """Head box from face keypoints when visible, else a conservative
    shoulder-relative estimate (better to over-blur a shoulder than miss a
    face that was too low-confidence to register)."""
    keypoints = pose.smoothed_keypoints or pose.keypoints
    conf = pose.keypoint_confidence

    visible = [keypoints[i] for i in _HEAD_KEYPOINT_IDXS if conf[i] >= _MIN_KEYPOINT_CONF]
    ls, rs = keypoints[_LEFT_SHOULDER], keypoints[_RIGHT_SHOULDER]
    shoulder_width = abs(rs[0] - ls[0])
    if conf[_LEFT_SHOULDER] < _MIN_KEYPOINT_CONF or conf[_RIGHT_SHOULDER] < _MIN_KEYPOINT_CONF or shoulder_width < 1:
        shoulder_width = max(abs(pose.xyxy[2] - pose.xyxy[0]) * 0.5, 10.0)

    if visible:
        xs = [p[0] for p in visible]
        ys = [p[1] for p in visible]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        radius = shoulder_width * 0.45
    else:
        # No confident face keypoints — estimate head as just above the
        # shoulder midpoint, sized relative to shoulder width.
        cx = (ls[0] + rs[0]) / 2
        cy = min(ls[1], rs[1]) - shoulder_width * 0.55
        radius = shoulder_width * 0.5

    return (int(cx - radius), int(cy - radius), int(cx + radius), int(cy + radius))


def blur_faces(image: np.ndarray, head_bboxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    out = image.copy()
    h, w = out.shape[:2]
    for x1, y1, x2, y2 in head_bboxes:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        roi = out[y1:y2, x1:x2]
        out[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (0, 0), sigmaX=max(8, (x2 - x1) / 4))
    return out


FrameEntry = Tuple[float, np.ndarray, list]  # (timestamp, image, head_bboxes)


class RollingFrameBuffer:
    """Keeps the last `max_seconds` of raw frames (+ every visible person's
    head bbox that frame, for blurring) so a confirmed alert can
    retroactively pull the clip that led to it — this is why it has to be
    long enough to cover a sustained-deviation event's full duration
    (observed up to ~25s in Stage 7 validation), not just a couple seconds."""

    def __init__(self, max_seconds: float = 35.0):
        self.max_seconds = max_seconds
        self._frames: Deque[FrameEntry] = deque()

    def add(self, timestamp: float, image: np.ndarray, head_bboxes: list) -> None:
        self._frames.append((timestamp, image.copy(), head_bboxes))
        cutoff = timestamp - self.max_seconds
        while self._frames and self._frames[0][0] < cutoff:
            self._frames.popleft()

    def extract(self, start_time: float, end_time: float, pad_seconds: float = 1.0) -> list[FrameEntry]:
        lo, hi = start_time - pad_seconds, end_time + pad_seconds
        return [entry for entry in self._frames if lo <= entry[0] <= hi]


def save_evidence_clip(frames: list[FrameEntry], clip_dir: Path, fps: float = 10.0) -> Optional[Path]:
    """Writes face-blurred frame_NNN.jpg + manifest.json into clip_dir.
    Returns the manifest path, or None if there were no frames to save."""
    if not frames:
        return None
    clip_dir.mkdir(parents=True, exist_ok=True)
    frame_names = []
    for i, (_, img, head_bboxes) in enumerate(frames):
        name = f"frame_{i:03d}.jpg"
        cv2.imwrite(str(clip_dir / name), blur_faces(img, head_bboxes), [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_names.append(name)

    manifest_path = clip_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"fps": fps, "frame_count": len(frame_names), "frames": frame_names}))
    return manifest_path
