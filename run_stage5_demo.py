"""End-to-end test for Stage 5: pose estimation + One-Euro smoothing.

Usage:
    python run_stage5_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv" \
        --output data/raw/stage5_out.mp4

Draws the COCO skeleton per tracked person (smoothed keypoints in green,
raw in faint red for comparison) and reports the torso-yaw proxy — the
robust-at-distance directional signal from docs/architecture.md §8, used
instead of fragile head/eye keypoints.
"""

from __future__ import annotations

import argparse
import time

import cv2

from ingestion.video_source import VideoSource
from perception.pose import PoseEstimator

SKELETON_EDGES = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),      # shoulders, arms
    (5, 11), (6, 12), (11, 12),                    # torso
    (11, 13), (13, 15), (12, 14), (14, 16),        # legs
    (0, 5), (0, 6),                                # neck-ish
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    video = VideoSource(source, target_fps=args.fps)
    estimator = PoseEstimator(confidence_threshold=args.conf, device=args.device)

    writer = None
    frame_count = 0
    t_start = time.monotonic()

    try:
        for frame in video.frames():
            poses = estimator.estimate(frame.image, timestamp=frame.timestamp)
            frame_count += 1

            elapsed = time.monotonic() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            summary = []
            for p in poses:
                yaw = p.torso_yaw_proxy()
                yaw_str = f"{yaw:+.2f}" if yaw is not None else "low-conf"
                summary.append(f"id{p.track_id}:torso_yaw={yaw_str}")
            print(f"frame {frame.frame_index}: " + "  ".join(summary) + f"  ({fps:.1f} fps)")

            if args.output:
                vis = frame.image.copy()
                for p in poses:
                    for a, b in SKELETON_EDGES:
                        if p.keypoint_confidence[a] > 0.3 and p.keypoint_confidence[b] > 0.3:
                            xa, ya = (p.smoothed_keypoints or p.keypoints)[a]
                            xb, yb = (p.smoothed_keypoints or p.keypoints)[b]
                            cv2.line(vis, (int(xa), int(ya)), (int(xb), int(yb)), (0, 220, 0), 2)
                    for (x, y), c in zip(p.keypoints, p.keypoint_confidence):
                        if c > 0.3:
                            cv2.circle(vis, (int(x), int(y)), 2, (0, 0, 220), -1)  # raw, faint red
                    for (x, y), c in zip(p.smoothed_keypoints or [], p.keypoint_confidence):
                        if c > 0.3:
                            cv2.circle(vis, (int(x), int(y)), 3, (0, 255, 0), -1)  # smoothed, green
                    x1, y1, _, _ = p.xyxy
                    cv2.putText(vis, f"id{p.track_id}", (int(x1), max(0, int(y1) - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
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


if __name__ == "__main__":
    main()
