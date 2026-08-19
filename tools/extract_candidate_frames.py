"""Extract candidate frames from staged/real footage for object-detector
labeling (docs/architecture.md §4 — the fine-tuned phone/paper/earpiece
detector needs a labeled dataset that a zero-shot approach can't substitute
for; confirmed by feasibility tests where both stock COCO and YOLO-World
open-vocabulary detection scored 0% hit rate on real phone-usage footage at
CCTV distance).

Samples one frame every --interval-sec from each video in --source-dir and
saves it for manual labeling (e.g. with LabelImg, CVAT, or Roboflow's
annotator). Deliberately dumb/uniform sampling rather than trying to guess
which frames contain the incident — the human labeler decides that; this
just keeps the labeling set to a manageable size instead of every frame.

Usage:
    python -m tools.extract_candidate_frames --source-dir data/test_videos --output-dir data/staged/candidate_frames --interval-sec 2
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}


def extract_from_video(video_path: Path, output_dir: Path, interval_sec: float) -> int:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    stride = max(1, round(fps * interval_sec))

    video_out_dir = output_dir / video_path.stem
    video_out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % stride == 0:
            timestamp_s = frame_idx / fps
            out_path = video_out_dir / f"frame_{timestamp_s:07.2f}s.jpg"
            cv2.imwrite(str(out_path), frame)
            saved += 1
        frame_idx += 1

    cap.release()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interval-sec", type=float, default=2.0)
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(p for p in source_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        print(f"No video files found in {source_dir}")
        return

    total = 0
    for video_path in videos:
        saved = extract_from_video(video_path, output_dir, args.interval_sec)
        total += saved
        print(f"{video_path.name}: {saved} frames -> {output_dir / video_path.stem}")

    print(f"\nTotal: {total} candidate frames extracted to {output_dir}")


if __name__ == "__main__":
    main()
