"""Part C validation (2026-08-21, pre-demo hardening): re-run the same
test videos from the earlier multi-video audit through the REAL pipeline
classes (PoseEstimator, GestureDetector, BaselineCalibrator, RiskEngine,
ObjectDetector), counting how many completed deviation/gesture events
would have alerted under the OLD policy (explanation is not None) vs how
many alert under the NEW, corroboration-tightened policy (is_alert).

Not a reimplementation - imports the actual production classes so this is
a genuine before/after of the real engine, not a simulation of it.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))

from behaviour.gestures import GestureDetector
from calibration.baseline import BaselineCalibrator, TemporalSample, compute_motion_magnitude
from calibration.homography import SeatCalibration
from calibration.quality import SeatAnchorQualityTracker
from perception.object_detector import ObjectDetector
from perception.pose import PoseEstimator, RIGHT_SHOULDER, LEFT_SHOULDER
from perception.roi_contraband import detect_in_roi, workspace_roi
from risk_engine.scorer import RiskEngine

FINE_TUNED_WEIGHTS = Path("data/weights/phone_detector_v1.pt")


def build_cal_04() -> SeatCalibration:
    cal = SeatCalibration(
        camera_id="video04", image_points=[(200, 195), (560, 260), (560, 150), (245, 105)],
        plane_points=[(0, 0), (400, 0), (400, 40), (0, 40)], max_snap_distance=60.0,
    )
    cal.seats = {
        "seat_1": cal.project((290, 210)), "seat_2": cal.project((370, 220)),
        "seat_3": cal.project((470, 230)), "seat_4": cal.project((550, 240)),
    }
    return cal


def build_cal_01() -> SeatCalibration:
    cal = SeatCalibration(
        camera_id="video01", image_points=[(550, 550), (1080, 550), (1080, 750), (550, 750)],
        plane_points=[(0, 0), (400, 0), (400, 150), (0, 150)], max_snap_distance=100.0,
    )
    cal.seats = {"seat_A": cal.project((970, 710)), "seat_B": cal.project((662, 593))}
    return cal


def build_cal_12() -> SeatCalibration:
    cal = SeatCalibration(
        camera_id="video12", image_points=[(560, 5), (848, 166), (814, 520), (0, 316)],
        plane_points=[(0, 0), (400, 0), (400, 500), (-600, 300)], max_snap_distance=150.0,
    )
    cal.seats = {
        "seat_A": cal.project((705, 520)), "seat_B": cal.project((782, 357)),
        "seat_C": cal.project((614, 140)), "seat_D": cal.project((122, 717)),
    }
    return cal


def run_video(name: str, path: str, cal: SeatCalibration, max_frames: int, image_size: tuple[int, int]) -> dict:
    w, h = image_size
    pose_est = PoseEstimator(device="cuda")
    weights = str(FINE_TUNED_WEIGHTS) if FINE_TUNED_WEIGHTS.exists() else "yolo11n.pt"
    obj_det = ObjectDetector(weights=weights, confidence_threshold=0.35, device="cuda")
    gesture_det = GestureDetector(cal)
    calibrator = BaselineCalibrator(settling_window_seconds=20.0)
    risk_engine = RiskEngine()
    anchor_quality = SeatAnchorQualityTracker(camera_id=name)
    prev_kp: dict[str, list] = {}

    cap = cv2.VideoCapture(path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(src_fps / 10.0))

    old_alert_count = 0
    new_alert_count = 0
    old_gesture_alert_count = 0  # pre-Part-A: every genuine gesture pushed unconditionally
    new_gesture_alert_count = 0  # post-Part-A: only if this seat's camera calibration is healthy
    n = 0
    sampled = 0
    while sampled < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if n % step != 0:
            continue
        t = sampled / 10.0
        sampled += 1

        poses = pose_est.estimate(frame, timestamp=t)
        object_detections = []
        if sampled % 5 == 0:
            for p in poses:
                roi = workspace_roi(p, w, h)
                if roi is not None:
                    object_detections.extend(detect_in_roi(obj_det, frame, roi))

        camera_healthy = anchor_quality.snapshot().status != "needs_attention"

        for p in poses:
            if p.track_id is None:
                continue
            x1, y1, x2, y2 = p.xyxy
            seat_id, _ = cal.nearest_seat(((x1 + x2) / 2.0, y2))
            anchor_quality.record(hit=seat_id is not None)
            if seat_id is None:
                continue

            gesture_active = False
            for gesture_event in gesture_det.observe(seat_id, p, t):
                if not gesture_event.likely_calibration_issue:
                    gesture_active = True
                    old_gesture_alert_count += 1  # pre-Part-A: pushed unconditionally
                    if camera_healthy:
                        new_gesture_alert_count += 1  # post-Part-A: gated on camera health

            keypoints = p.smoothed_keypoints or p.keypoints
            shoulder_w = abs(keypoints[RIGHT_SHOULDER][0] - keypoints[LEFT_SHOULDER][0]) or 1.0
            motion = 0.0
            if seat_id in prev_kp:
                motion = compute_motion_magnitude(prev_kp[seat_id], keypoints, p.keypoint_confidence, shoulder_w)
            prev_kp[seat_id] = keypoints

            sample = TemporalSample(timestamp=t, torso_yaw=p.hybrid_torso_yaw(w, h), motion_magnitude=motion)
            calibrator.observe(seat_id, sample)
            if not calibrator.is_calibrated(seat_id):
                continue

            baseline = calibrator.baseline(seat_id)
            yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
            motion_z = baseline.motion_zscore(sample.motion_magnitude)

            object_label, object_conf = None, 0.0
            for det in object_detections:
                dx1, dy1, dx2, dy2 = det.xyxy
                center = ((dx1 + dx2) / 2, (dy1 + dy2) / 2)
                if cal.nearest_seat(center)[0] == seat_id:
                    object_label, object_conf = det.label, det.confidence
                    break

            assessment = risk_engine.observe(
                seat_id=seat_id, timestamp=t, yaw_zscore=yaw_z, motion_zscore=motion_z,
                baseline_yaw_mean=baseline.torso_yaw_mean, baseline_yaw_std=baseline.torso_yaw_std,
                object_label=object_label, object_confidence=object_conf, gesture_active=gesture_active,
            )
            if assessment.explanation:
                old_alert_count += 1
                if assessment.is_alert and camera_healthy:
                    new_alert_count += 1

    return {
        "frames": sampled,
        "old_alert_count": old_alert_count + old_gesture_alert_count,
        "new_alert_count": new_alert_count + new_gesture_alert_count,
        "old_deviation_alerts": old_alert_count,
        "new_deviation_alerts": new_alert_count,
        "old_gesture_alerts": old_gesture_alert_count,
        "new_gesture_alerts": new_gesture_alert_count,
    }


if __name__ == "__main__":
    # Full video length (at 10fps sampling) for each - the earlier 250-
    # frame (25s) window left almost no time after the 20s settling window
    # for a sustained deviation to actually accumulate, which produced a
    # meaningless 0/0 result on the first attempt.
    cases = [
        ("04_baseline", "data/test_videos/04.CCTV Candidate Talking.mkv", build_cal_04(), 1430, (640, 480)),
        ("01_computer_lab", "data/test_videos/01.Candidate was found using a mobile phone in the examination hall..mkv", build_cal_01(), 1310, (1280, 720)),
        ("12_dense_classroom", "data/test_videos/Seat No. 12 was seen taking a piece of paper from the desk.mkv", build_cal_12(), 880, (1280, 720)),
    ]
    print("video05_reception has no desks/seats — not applicable to seat-scoped alert testing (documented in the original Part 1 audit).")
    print()
    for name, path, cal, max_frames, size in cases:
        t0 = time.time()
        result = run_video(name, path, cal, max_frames, size)
        elapsed = time.time() - t0
        old_total, new_total = result["old_alert_count"], result["new_alert_count"]
        reduction = 100 * (1 - new_total / old_total) if old_total else 0.0
        print(f"=== {name} ===  frames={result['frames']}  ({elapsed:.0f}s)")
        print(f"  deviation-based: OLD={result['old_deviation_alerts']}  NEW={result['new_deviation_alerts']}")
        print(f"  gesture-based:   OLD={result['old_gesture_alerts']}  NEW={result['new_gesture_alerts']}")
        print(f"  TOTAL:           OLD={old_total}  NEW={new_total}  reduction={reduction:.0f}%")
        print()
