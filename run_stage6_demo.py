"""End-to-end test for Stage 6: per-seat temporal buffer + baseline
calibration.

Usage:
    python run_stage6_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv" \
        --calibration data/raw/cam04_illustrative_calibration.json \
        --settling-seconds 15

--settling-seconds is deliberately short here for demo purposes (a real exam
uses ~150s per docs/architecture.md §5); pass the real value for production.

For each seat: shows the calibration settling window filling up, then once
calibrated, reports the live z-score deviation from that seat's own
baseline — the mechanism, not a real threshold decision (that's Stage 7,
the risk engine).
"""

from __future__ import annotations

import argparse

from calibration.baseline import BaselineCalibrator, SeatTemporalBuffer, TemporalSample, compute_motion_magnitude
from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.pose import PoseEstimator, LEFT_SHOULDER, RIGHT_SHOULDER


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--settling-seconds", type=float, default=15.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    seat_cal = SeatCalibration.from_json(args.calibration)
    video = VideoSource(source, target_fps=args.fps)
    pose_estimator = PoseEstimator(confidence_threshold=args.conf, device=args.device)
    calibrator = BaselineCalibrator(settling_window_seconds=args.settling_seconds)
    buffers: dict[str, SeatTemporalBuffer] = {}
    prev_keypoints: dict[str, list[tuple[float, float]]] = {}  # keyed by seat_id, for motion calc

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
                seat_id, dist = seat_cal.nearest_seat(anchor)
                if seat_id is None:
                    continue  # not anchored to any known seat, skip

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
                buffers.setdefault(seat_id, SeatTemporalBuffer()).add(sample)
                calibrator.observe(seat_id, sample)

                if calibrator.is_calibrated(seat_id):
                    baseline = calibrator.baseline(seat_id)
                    yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
                    motion_z = baseline.motion_zscore(sample.motion_magnitude)
                    yaw_z_str = f"{yaw_z:+.2f}" if yaw_z is not None else "n/a"
                    print(f"frame {frame.frame_index} {seat_id}: CALIBRATED yaw_z={yaw_z_str} motion_z={motion_z:+.2f}")
                else:
                    progress = calibrator.calibration_progress(seat_id, frame.timestamp)
                    print(f"frame {frame.frame_index} {seat_id}: calibrating ({progress*100:.0f}%)")

            if args.max_frames and frame_count >= args.max_frames:
                break
    finally:
        video.release()

    print("\n--- baseline summary ---")
    for seat_id in sorted(buffers.keys()):
        baseline = calibrator.baseline(seat_id)
        if baseline:
            print(
                f"{seat_id}: yaw_mean={baseline.torso_yaw_mean:+.2f} yaw_std={baseline.torso_yaw_std:.2f}  "
                f"motion_mean={baseline.motion_mean:.3f} motion_std={baseline.motion_std:.3f}"
            )
        else:
            print(f"{seat_id}: never finished calibrating in this clip")


if __name__ == "__main__":
    main()
