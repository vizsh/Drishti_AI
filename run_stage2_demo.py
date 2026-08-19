"""End-to-end test for Stage 2: person detection + BoT-SORT tracking.

Usage:
    python run_stage2_demo.py --source "data/test_videos/04.CCTV Candidate Talking.mkv" --output data/raw/stage2_out.mp4

Draws a persistent-colored box + track ID per person and writes an annotated
video so track-ID stability can be reviewed visually (does an ID survive a
person being briefly occluded, or does it swap to a new number?). Also prints
a summary: unique track IDs seen and max concurrent tracks, as a first-pass
signal of ID-switching behaviour.
"""

from __future__ import annotations

import argparse
import time

import cv2
import numpy as np

from ingestion.video_source import VideoSource
from perception.tracker import PersonTracker


def color_for_id(track_id: int) -> tuple[int, int, int]:
    rng = np.random.default_rng(track_id)
    return tuple(int(c) for c in rng.integers(60, 255, size=3))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", default=None, help="Path to save annotated video (mp4)")
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N processed frames")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source: str | int = int(args.source) if args.source.isdigit() else args.source

    video = VideoSource(source, target_fps=args.fps)
    tracker = PersonTracker(confidence_threshold=args.conf, device=args.device)

    writer = None
    frame_count = 0
    seen_ids: set[int] = set()
    max_concurrent = 0
    t_start = time.monotonic()

    try:
        for frame in video.frames():
            tracks = tracker.track(frame.image)
            frame_count += 1

            ids_this_frame = {t.track_id for t in tracks}
            seen_ids |= ids_this_frame
            max_concurrent = max(max_concurrent, len(ids_this_frame))

            elapsed = time.monotonic() - t_start
            fps = frame_count / elapsed if elapsed > 0 else 0.0
            print(
                f"frame {frame.frame_index}: {len(tracks)} tracked  "
                f"ids={sorted(ids_this_frame)}  ({fps:.1f} fps processed)"
            )

            if args.output:
                vis = frame.image.copy()
                for t in tracks:
                    x1, y1, x2, y2 = (int(v) for v in t.xyxy)
                    color = color_for_id(t.track_id)
                    cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(
                        vis, f"#{t.track_id} {t.confidence:.2f}", (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
                    )
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

    print(f"\n--- summary ---\nframes processed: {frame_count}")
    print(f"unique track IDs seen: {len(seen_ids)} -> {sorted(seen_ids)}")
    print(f"max concurrent tracks in a single frame: {max_concurrent}")


if __name__ == "__main__":
    main()
