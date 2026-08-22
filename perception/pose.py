"""Stage 5: pose estimation.

YOLO11-pose, chosen over MediaPipe/OpenPose/ViTPose (docs/architecture.md
§2): MediaPipe underperforms in the dense/occluded scenes a real exam hall
produces; OpenPose is non-commercial-licensed; ViTPose needs server-GPU
compute. COCO-pretrained weights are used as-is — no fine-tuning needed for
body keypoints.

Runs its own person detection + BoT-SORT tracking internally (the pose model
ships with a built-in detector), independent of perception/detector.py's
person-only branch — this matches the pipeline's parallel-branch design
(docs/architecture.md §11), where detect+track and pose are separate model
passes that get fused downstream via seat-anchored identity, not merged into
one model here.

COCO 17-keypoint layout (index: name):
 0 nose, 1 left_eye, 2 right_eye, 3 left_ear, 4 right_ear,
 5 left_shoulder, 6 right_shoulder, 7 left_elbow, 8 right_elbow,
 9 left_wrist, 10 right_wrist, 11 left_hip, 12 right_hip,
 13 left_knee, 14 right_knee, 15 left_ankle, 16 right_ankle
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from ultralytics import YOLO

from perception.one_euro_filter import KeypointSmoother
from perception.head_pose import solve_head_pose

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_HIP, RIGHT_HIP = 11, 12


@dataclass
class PoseResult:
    track_id: Optional[int]
    xyxy: tuple[float, float, float, float]
    confidence: float
    keypoints: list[tuple[float, float]]       # raw, length 17
    keypoint_confidence: list[float]           # per-keypoint confidence, length 17
    smoothed_keypoints: Optional[list[tuple[float, float]]] = None

    def keypoint(self, name: str, smoothed: bool = True) -> Optional[tuple[float, float, float]]:
        idx = KEYPOINT_NAMES.index(name)
        pts = self.smoothed_keypoints if (smoothed and self.smoothed_keypoints) else self.keypoints
        x, y = pts[idx]
        return (x, y, self.keypoint_confidence[idx])

    def torso_yaw_proxy(self) -> Optional[float]:
        """Shoulder-to-hip midpoint x-offset as a torso-orientation proxy.

        docs/architecture.md §8: at CCTV distance, fine head/eye keypoints
        have too few usable pixels to be reliable. Torso/shoulder geometry is
        the more robust primary directional signal; this returns None when
        confidence is too low to trust, so callers can fall back correctly
        rather than silently trusting noise.
        """
        min_conf = 0.4
        idxs = [LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP]
        if any(self.keypoint_confidence[i] < min_conf for i in idxs):
            return None
        pts = self.smoothed_keypoints or self.keypoints
        ls, rs, lh, rh = (pts[i] for i in idxs)
        shoulder_mid_x = (ls[0] + rs[0]) / 2.0
        hip_mid_x = (lh[0] + rh[0]) / 2.0
        shoulder_width = abs(rs[0] - ls[0]) or 1.0
        return (shoulder_mid_x - hip_mid_x) / shoulder_width

    def hybrid_torso_yaw(self, image_width: int, image_height: int) -> Optional[float]:
        """Phase 2a (2026-08-21): completes the originally-planned hybrid
        head-pose fallback. Runs a PnP solve (perception/head_pose.py) on
        face keypoints when they're confidently detected — a materially
        more precise directional signal than the shoulder/hip proxy — and
        falls back to torso_yaw_proxy() EXACTLY as it worked before
        whenever face keypoints aren't good enough. Purely additive:
        torso_yaw_proxy() itself is untouched.

        The PnP yaw (degrees) is divided by 90 to land on roughly the same
        numeric scale torso_yaw_proxy()'s shoulder-width-normalized ratio
        uses. This matters beyond cosmetics: baseline calibration is a
        per-seat z-score over whatever this method returns, computed over a
        mix of frames that may use either source (a student's face keypoints
        can go from confident to occluded frame-to-frame) — without a
        comparable scale, switching sources mid-session would corrupt that
        seat's baseline statistics with two incompatible units.
        """
        keypoints = self.smoothed_keypoints or self.keypoints
        head_pose = solve_head_pose(keypoints, self.keypoint_confidence, image_width, image_height)
        if head_pose is not None:
            return head_pose.yaw_deg / 90.0
        return self.torso_yaw_proxy()

    def detection_confidence(self) -> float:
        """Overall reliability of this frame's pose for behaviour scoring —
        not the same thing as risk_score. PS #1's explainability requirement
        (updated PDF, "Explainability and Human Oversight") lists confidence
        scores alongside behavioural explanations and event timelines as a
        required output: an alert must say how reliable its own inputs were,
        not just what it concluded. Averages the keypoints that actually
        drive Stage 6-8's signals (shoulders/hips for torso_yaw, wrists for
        hand_reach_across) rather than all 17 — ankle confidence, for
        instance, is irrelevant to any behaviour signal this system computes.
        """
        idxs = [LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP, 9, 10]  # + wrists
        values = [self.keypoint_confidence[i] for i in idxs]
        return sum(values) / len(values)


class PoseEstimator:
    def __init__(
        self,
        weights: str = "yolo11n-pose.pt",
        confidence_threshold: float = 0.4,
        device: Optional[str] = None,
        tracker_config: str = "botsort.yaml",
        smooth: bool = True,
    ):
        self.model = YOLO(weights)
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.tracker_config = tracker_config
        self.smoother = KeypointSmoother(num_keypoints=17) if smooth else None

    def estimate(self, image: np.ndarray, timestamp: float = 0.0) -> List[PoseResult]:
        results = self.model.track(
            image,
            conf=self.confidence_threshold,
            device=self.device,
            quantize="fp16" if self.device == "cuda" else None,
            tracker=self.tracker_config,
            persist=True,
            verbose=False,
        )
        out: List[PoseResult] = []
        r = results[0]
        if r.keypoints is None or len(r.boxes) == 0:
            return out

        track_ids = r.boxes.id
        for i in range(len(r.boxes)):
            box = r.boxes[i]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            track_id = int(track_ids[i]) if track_ids is not None else None

            kp_xy = r.keypoints.xy[i].tolist()
            kp_conf = r.keypoints.conf[i].tolist() if r.keypoints.conf is not None else [1.0] * len(kp_xy)
            keypoints = [(float(x), float(y)) for x, y in kp_xy]

            smoothed = None
            if self.smoother is not None and track_id is not None:
                smoothed = self.smoother.smooth(track_id, keypoints, timestamp)

            out.append(
                PoseResult(
                    track_id=track_id,
                    xyxy=(x1, y1, x2, y2),
                    confidence=conf,
                    keypoints=keypoints,
                    keypoint_confidence=[float(c) for c in kp_conf],
                    smoothed_keypoints=smoothed,
                )
            )
        return out
