"""Feasibility test for Stage 4: does stock COCO cell-phone detection catch
real phone use at CCTV distance?

Usage:
    python run_stage4_demo.py --source "data/test_videos/01.Candidate was found using a mobile phone in the examination hall..mkv" \
        --output data/raw/stage4_out.mp4

This is a feasibility probe, not the production object detector — COCO's
"cell phone"/"book" classes are a free baseline, not a validated exam-
contraband model. Report what fraction of frames get a hit and at what
confidence, so the real question ("do we need to fine-tune, and how badly")
gets an honest, measured answer instead of an assumption.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter

import cv2

from ingestion.video_source import VideoSource
from perception.object_detector import ObjectDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    video = VideoSource(source, target_fps=args.fps)
    detector = ObjectDetector(confidence_threshold=args.conf, device=args.device)

    writer = None
    frame_count = 0
    hit_count = 0
    label_counts: Counter[str] = Counter()
    max_conf_seen: dict[str, float] = {}
    t_start = time.monotonic()

    try:
        for frame in video.frames():
            detections = detector.detect(frame.image)
            frame_count += 1
            if detections:
                hit_count += 1
            for d in detections:
                label_counts[d.label] += 1
                max_conf_seen[d.label] = max(max_conf_seen.get(d.label, 0.0), d.confidence)

            elapsed = time.monotonic() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            summary = ", ".join(f"{d.label}={d.confidence:.2f}" for d in detections) or "none"
            print(f"frame {frame.frame_index}: {summary}  ({fps:.1f} fps)")

            if args.output:
                vis = frame.image.copy()
                for d in detections:
                    x1, y1, x2, y2 = (int(v) for v in d.xyxy)
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 140, 255), 2)
                    cv2.putText(vis, f"{d.label} {d.confidence:.2f}", (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)
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

    print("\n--- feasibility summary ---")
    print(f"frames processed: {frame_count}")
    print(f"frames with >=1 detection: {hit_count} ({100 * hit_count / max(frame_count,1):.1f}%)")
    for label, count in label_counts.most_common():
        print(f"  {label}: {count} detections, max confidence {max_conf_seen[label]:.2f}")


if __name__ == "__main__":
    main()
