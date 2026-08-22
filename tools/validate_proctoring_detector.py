"""Honest before/after check: does the fine-tuned proctoring detector
(tools/train_proctoring_detector.py's output) actually do better than the
stock COCO yolo11n.pt "cell phone" class already running in production,
on THIS project's own real ground-truth footage — not a training-loss
number, the same methodology the 2026-08-22 accuracy audit used.

Checks two things per model, per video:
  - Peak confidence and hit-rate during the video's real phone-use window
    (recall — does it actually see the phone that's there)
  - False-positive rate on data/test_videos/04, which has NO real phone,
    only a static water bottle that the stock detector historically
    misread as "cell phone" (precision — does it avoid the known trap)

Prints a plain comparison table. Does not modify any production config —
swapping the weights in is a separate, deliberate step taken only if this
script shows a real improvement.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from perception.object_detector import ObjectDetector

STOCK_WEIGHTS = "yolo11n.pt"
STOCK_CLASSES = {67: "cell phone"}

FINETUNED_WEIGHTS = "data/weights/proctoring_v1.pt"

VIDEOS = {
    "01 (real phone use)": ("data/test_videos/01.Candidate was found using a mobile phone in the examination hall..mkv", True),
    "02 (real phone use)": None,  # filled in below if it exists
    "04 (no phone, static bottle trap)": ("data/test_videos/04.CCTV Candidate Talking.mkv", False),
}


def find_video(pattern: str) -> Path | None:
    matches = list(Path("data/test_videos").glob(pattern))
    return matches[0] if matches else None


def resolve_finetuned_classes(weights_path: str) -> dict[int, str]:
    from ultralytics import YOLO

    names = YOLO(weights_path).names
    # Keep only the classes this project actually cares about as contraband.
    wanted = {"cell phone", "phone", "laptop", "book", "headphone", "tv"}
    return {i: n for i, n in names.items() if n.lower() in wanted}


def scan_video(detector: ObjectDetector, video_path: Path, sample_every: int = 5) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    frame_i = 0
    hits = 0
    checked = 0
    peak_conf = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_i += 1
        if frame_i % sample_every != 0:
            continue
        checked += 1
        dets = detector.detect(frame)
        phone_dets = [d for d in dets if "phone" in d.label.lower()]
        if phone_dets:
            hits += 1
            peak_conf = max(peak_conf, max(d.confidence for d in phone_dets))
    cap.release()
    return {"checked_frames": checked, "hit_frames": hits, "hit_rate": hits / checked if checked else 0.0, "peak_conf": peak_conf}


def main() -> None:
    video_02 = find_video("02*")
    videos = {
        "01 (real phone use)": (find_video("01*"), True),
        "04 (no phone, static bottle trap)": (find_video("04*"), False),
    }
    if video_02:
        videos["02 (real phone use)"] = (video_02, True)

    stock = ObjectDetector(weights=STOCK_WEIGHTS, classes=STOCK_CLASSES, confidence_threshold=0.05, device="cuda")

    finetuned = None
    if Path(FINETUNED_WEIGHTS).exists():
        ft_classes = resolve_finetuned_classes(FINETUNED_WEIGHTS)
        finetuned = ObjectDetector(weights=FINETUNED_WEIGHTS, classes=ft_classes, confidence_threshold=0.05, device="cuda")
    else:
        print(f"WARNING: {FINETUNED_WEIGHTS} not found — run tools/train_proctoring_detector.py first. Showing stock-only baseline.")

    print(f"\n{'video':<38}{'model':<12}{'checked':<9}{'hit_rate':<10}{'peak_conf':<10}{'expects_phone'}")
    print("-" * 90)
    for name, (path, expects_phone) in videos.items():
        if path is None:
            print(f"{name:<38}(video file not found — skipped)")
            continue
        for label, det in (("stock", stock), ("finetuned", finetuned)):
            if det is None:
                continue
            r = scan_video(det, path)
            print(f"{name:<38}{label:<12}{r['checked_frames']:<9}{r['hit_rate']:.2%}    {r['peak_conf']:.3f}     {expects_phone}")

    print(
        "\nReading this: for the phone-use videos, higher hit_rate/peak_conf = better recall (good). "
        "For video 04 (no real phone), LOWER hit_rate = better precision (fewer false alarms on the "
        "known static-object trap) — a model that scores worse there is actively harmful, not neutral."
    )


if __name__ == "__main__":
    main()
