"""End-to-end test for Stage 0-1: ingestion + person detection.

Usage:
    python run_stage1_demo.py --source path/to/video.mp4
    python run_stage1_demo.py --source 0                      # webcam
    python run_stage1_demo.py --source rtsp://ip:554/stream1  # RTSP camera

Draws person bounding boxes and shows a live window. Press 'q' to quit.
Pass --headless to skip the window and just print detection counts + FPS
(useful over SSH or when no display is available).
"""

from __future__ import annotations

import argparse
import time

import cv2

from ingestion.video_source import VideoSource
from perception.detector import PersonDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Video file path, webcam index, or RTSP URL")
    parser.add_argument("--fps", type=float, default=10.0, help="Target processing frame rate")
    parser.add_argument("--conf", type=float, default=0.4, help="Detection confidence threshold")
    parser.add_argument("--device", default=None, help="'cuda', 'cpu', or None to auto-select")
    parser.add_argument("--headless", action="store_true", help="Don't open a display window")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    video = VideoSource(source, target_fps=args.fps)
    detector = PersonDetector(confidence_threshold=args.conf, device=args.device)

    frame_count = 0
    t_start = time.monotonic()

    try:
        for frame in video.frames():
            detections = detector.detect(frame.image)
            frame_count += 1

            elapsed = time.monotonic() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            print(f"frame {frame.frame_index}: {len(detections)} person(s)  ({fps:.1f} fps processed)")

            if not args.headless:
                vis = frame.image.copy()
                for det in detections:
                    x1, y1, x2, y2 = (int(v) for v in det.xyxy)
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 0), 2)
                    cv2.putText(
                        vis, f"{det.confidence:.2f}", (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1,
                    )
                cv2.putText(vis, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                cv2.imshow("KINESIS AI - Stage 1: person detection", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        video.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
