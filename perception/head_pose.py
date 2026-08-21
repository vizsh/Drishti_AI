"""Stage 5b: hybrid head-pose solver (Phase 2a, 2026-08-21 accuracy pass).

Completes the originally-planned fallback design referenced in
docs/architecture.md §8: torso_yaw_proxy() (perception/pose.py) is the
robust default because at CCTV distance, face keypoints often don't have
enough usable pixels to trust — but when nose/eyes/ears ARE confidently
detected, a proper PnP solve gives a materially more precise head-
orientation signal than the coarse shoulder/hip-offset proxy. Purely
additive: torso_yaw_proxy() itself is unchanged and still the fallback,
used exactly as it worked before whenever face keypoints aren't good
enough (occluded, too distant, low confidence).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# Generic anthropometric 3D face model (mm, arbitrary but consistent scale
# — PnP's rotation output is scale-invariant). Only the 5 points COCO pose
# actually gives us: nose, both eyes, both ears. No chin/mouth keypoints
# exist in this keypoint set, so this is a 5-point solve, not the classic
# 6-point (nose+chin+eyes+mouth-corners) head-pose model.
MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),  # nose tip
        (-30.0, 32.0, -26.0),  # left eye
        (30.0, 32.0, -26.0),  # right eye
        (-77.0, 0.0, -73.0),  # left ear
        (77.0, 0.0, -73.0),  # right ear
    ],
    dtype=np.float64,
)

# Indices into perception/pose.py's KEYPOINT_NAMES for the 5 face points,
# in the same order as MODEL_POINTS above.
FACE_KEYPOINT_IDXS = (0, 1, 2, 3, 4)  # nose, left_eye, right_eye, left_ear, right_ear
MIN_FACE_CONFIDENCE = 0.4


@dataclass
class HeadPose:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float


def solve_head_pose(
    keypoints: list[tuple[float, float]],
    keypoint_confidence: list[float],
    image_width: int,
    image_height: int,
    min_conf: float = MIN_FACE_CONFIDENCE,
) -> Optional[HeadPose]:
    """PnP-based head yaw/pitch/roll from face keypoints, or None if any of
    nose/left_eye/right_eye/left_ear/right_ear is below min_conf — the
    signal callers should treat as "not confident enough, fall back to
    torso_yaw_proxy()" per the hybrid design."""
    if any(keypoint_confidence[i] < min_conf for i in FACE_KEYPOINT_IDXS):
        return None

    image_points = np.array([keypoints[i] for i in FACE_KEYPOINT_IDXS], dtype=np.float64)

    # No real per-camera intrinsic calibration exists yet (a separate,
    # larger deployment step - see docs/rtsp_readiness.md's fisheye-
    # undistortion gap) - focal length approximated as image width, a
    # standard simplification for head-pose PnP without a proper camera
    # calibration. Good enough for relative yaw/pitch/roll, not for
    # absolute 3D position or metric distance.
    focal_length = float(image_width)
    center = (image_width / 2.0, image_height / 2.0)
    camera_matrix = np.array(
        [[focal_length, 0, center[0]], [0, focal_length, center[1]], [0, 0, 1]], dtype=np.float64
    )
    dist_coeffs = np.zeros((4, 1))

    ok, rotation_vec, _ = cv2.solvePnP(
        MODEL_POINTS, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_EPNP
    )
    if not ok:
        return None

    rotation_mat, _ = cv2.Rodrigues(rotation_vec)
    pose_mat = cv2.hconcat([rotation_mat, np.zeros((3, 1))])
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)
    pitch, yaw, roll = (float(a) for a in euler_angles.flatten())
    return HeadPose(yaw_deg=yaw, pitch_deg=pitch, roll_deg=roll)
