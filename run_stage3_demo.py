"""End-to-end test for Stage 3: tracking + seat-anchored identity.

Usage:
    python run_stage3_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv" \
        --calibration data/raw/cam04_illustrative_calibration.json \
        --output data/raw/stage3_out.mp4

Requires a calibration JSON produced by calibration/calibrate_tool.py (or
SeatCalibration.to_json). Annotates each detection with its snapped seat_id
instead of the raw tracker ID, and prints both side by side so seat-anchoring
stability can be compared directly against the Stage 2 track-ID churn.
"""

from __future__ import annotations

import argparse
import time

import cv2

from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.tracker import PersonTracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    cal = SeatCalibration.from_json(args.calibration)
    video = VideoSource(source, target_fps=args.fps)
    tracker = PersonTracker(confidence_threshold=args.conf, device=args.device)

    writer = None
    frame_count = 0
    seat_id_sets_over_time: dict[str, set[int]] = {}  # seat_id -> set of track_ids ever assigned to it
    t_start = time.monotonic()

    try:
        for frame in video.frames():
            tracks = tracker.track(frame.image)
            frame_count += 1

            elapsed = time.monotonic() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            line = f"frame {frame.frame_index}: "
            annotations = []

            vis = frame.image.copy() if args.output else None
            for t in tracks:
                # bbox lower point: closest visible point to the desk surface
                # in this camera angle (feet are occluded under the desk).
                x1, y1, x2, y2 = t.xyxy
                anchor = ((x1 + x2) / 2.0, y2)
                seat_id, dist = cal.nearest_seat(anchor)

                label = seat_id if seat_id else "unmatched"
                annotations.append(f"track#{t.track_id}->{label}({dist:.0f})")
                if seat_id:
                    seat_id_sets_over_time.setdefault(seat_id, set()).add(t.track_id)

                if vis is not None:
                    xi1, yi1, xi2, yi2 = (int(v) for v in t.xyxy)
                    color = (0, 200, 0) if seat_id else (0, 0, 200)
                    cv2.rectangle(vis, (xi1, yi1), (xi2, yi2), color, 2)
                    cv2.putText(
                        vis, label, (xi1, max(0, yi1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
                    )

            print(line + "  ".join(annotations) + f"  ({fps:.1f} fps)")

            if vis is not None:
                if writer is None:
                    h, w = vis.shape[:2]
                    writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (w, h))
                writer.write(vis)

            if args.max_frames and frame_count >= args.max_frames:
                break
    finally:
        video.release()
        if writer is not None:
            writer.release()

    print("\n--- seat-anchoring stability summary ---")
    for seat_id, track_ids in sorted(seat_id_sets_over_time.items()):
        print(f"{seat_id}: {len(track_ids)} distinct tracker ID(s) seen -> {sorted(track_ids)}")
    print("(Stage 2 alone churned through 10 distinct track IDs for what was")
    print(" visually the same handful of people. Compare each seat's ID count above.)")


if __name__ == "__main__":
    main()
