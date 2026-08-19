"""End-to-end test for Stage 7: the risk fusion engine.

Usage:
    python run_stage7_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv" --settling-seconds 8

Builds an illustrative calibration inline (same points as Stage 3's demo —
not accurate, just enough seats to exercise the pipeline) rather than
depending on a file, so this script is self-contained. Prints a risk score
per seat per frame, and the full template-based explanation whenever a
sustained deviation event fires.
"""

from __future__ import annotations

import argparse

from calibration.baseline import BaselineCalibrator, SeatTemporalBuffer, TemporalSample, compute_motion_magnitude
from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.pose import LEFT_SHOULDER, RIGHT_SHOULDER, PoseEstimator
from risk_engine.scorer import RiskEngine


def build_illustrative_calibration() -> SeatCalibration:
    cal = SeatCalibration(
        camera_id="cam04_illustrative",
        image_points=[(200, 195), (560, 260), (560, 150), (245, 105)],
        plane_points=[(0, 0), (400, 0), (400, 40), (0, 40)],
        max_snap_distance=60,
    )
    for seat_id, img_pt in {
        "seat_1": (290, 210),
        "seat_2": (370, 220),
        "seat_3": (470, 230),
        "seat_4": (550, 240),
    }.items():
        cal.seats[seat_id] = cal.project(img_pt)
    return cal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--settling-seconds", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--alert-threshold", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    seat_cal = build_illustrative_calibration()
    video = VideoSource(source, target_fps=args.fps)
    pose_estimator = PoseEstimator(confidence_threshold=args.conf, device=args.device)
    calibrator = BaselineCalibrator(settling_window_seconds=args.settling_seconds)
    risk_engine = RiskEngine()
    prev_keypoints: dict[str, list[tuple[float, float]]] = {}

    alerts_fired = 0
    frame_count = 0
    try:
        for frame in video.frames():
            poses = pose_estimator.estimate(frame.image, timestamp=frame.timestamp)
            frame_count += 1

            for p in poses:
                if p.track_id is None:
                    continue
                x1, y1, x2, y2 = p.xyxy
                anchor = ((x1 + x2) / 2.0, y2)
                seat_id, _ = seat_cal.nearest_seat(anchor)
                if seat_id is None:
                    continue

                keypoints = p.smoothed_keypoints or p.keypoints
                shoulder_width = abs(keypoints[RIGHT_SHOULDER][0] - keypoints[LEFT_SHOULDER][0]) or 1.0
                motion = 0.0
                if seat_id in prev_keypoints:
                    motion = compute_motion_magnitude(
                        prev_keypoints[seat_id], keypoints, p.keypoint_confidence, shoulder_width
                    )
                prev_keypoints[seat_id] = keypoints

                sample = TemporalSample(
                    timestamp=frame.timestamp, torso_yaw=p.torso_yaw_proxy(), motion_magnitude=motion
                )
                calibrator.observe(seat_id, sample)
                if not calibrator.is_calibrated(seat_id):
                    continue

                baseline = calibrator.baseline(seat_id)
                yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
                motion_z = baseline.motion_zscore(sample.motion_magnitude)

                assessment = risk_engine.observe(
                    seat_id=seat_id,
                    timestamp=frame.timestamp,
                    yaw_zscore=yaw_z,
                    motion_zscore=motion_z,
                    baseline_yaw_mean=baseline.torso_yaw_mean,
                    baseline_yaw_std=baseline.torso_yaw_std,
                    object_label=None,  # Stage 4 detector not trustworthy yet — wired in once labeled data lands
                )

                if assessment.explanation:
                    alerts_fired += 1
                    print(f"\n[ALERT] frame {frame.frame_index} {seat_id} risk={assessment.risk_score:.2f}")
                    print(f"        {assessment.explanation}")
                elif assessment.risk_score >= args.alert_threshold:
                    print(f"frame {frame.frame_index} {seat_id}: risk={assessment.risk_score:.2f} (elevated, no event yet)")

            if args.max_frames and frame_count >= args.max_frames:
                break
    finally:
        video.release()

    print(f"\n--- summary --- frames={frame_count} alerts_fired={alerts_fired}")


if __name__ == "__main__":
    main()
