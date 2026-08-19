"""End-to-end test for Stage 8: rule-based named-gesture detection.

Usage:
    python run_stage8_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv"

Runs pose + seat-anchoring + GestureDetector against real footage and
prints any hand_reach_across / sustained_lean events with their template
explanation — the same footage already used for Stages 2/3/5/6/7, so
results here are directly comparable.
"""

from __future__ import annotations

import argparse

from behaviour.gestures import GestureDetector, explain_gesture
from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.pose import PoseEstimator


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
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    seat_cal = build_illustrative_calibration()
    video = VideoSource(source, target_fps=args.fps)
    pose_estimator = PoseEstimator(confidence_threshold=args.conf, device=args.device)
    gesture_detector = GestureDetector(seat_cal)

    frame_count = 0
    events_fired = 0
    try:
        for frame in video.frames():
            poses = pose_estimator.estimate(frame.image, timestamp=frame.frame_index / args.fps)
            frame_count += 1

            for p in poses:
                if p.track_id is None:
                    continue
                x1, y1, x2, y2 = p.xyxy
                anchor = ((x1 + x2) / 2.0, y2)
                seat_id, _ = seat_cal.nearest_seat(anchor)
                if seat_id is None:
                    continue

                for event in gesture_detector.observe(seat_id, p, frame.frame_index / args.fps):
                    events_fired += 1
                    print(f"\n[GESTURE] frame {frame.frame_index} {event.gesture}")
                    print(f"          {explain_gesture(event)}")

            if args.max_frames and frame_count >= args.max_frames:
                break
    finally:
        video.release()

    print(f"\n--- summary --- frames={frame_count} gesture_events={events_fired}")


if __name__ == "__main__":
    main()
