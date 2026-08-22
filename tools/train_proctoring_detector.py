"""Fine-tunes a phone/laptop/book/headphone/tv contraband detector on the
real, public "Online Proctoring System" dataset (Roboflow Universe,
online-exam-cheating-detection-kvdul/online-proctoring-system-x27ou-e7abr,
10,213 images, CC BY 4.0) — the dataset check this session ran confirmed
real per-object bounding-box annotations (not whole-frame behavior labels)
for exactly the classes docs/architecture.md's contraband detector always
wanted: cell phone, laptop, book, headphone (a real earpiece proxy), tv.

Starts from yolo11n.pt (COCO-pretrained), matching the weights already
running in production (perception/object_detector.py) — this is a
fine-tune, not a from-scratch train, so it keeps everything COCO-pretrained
detection already does well and specializes it on this domain's real data.

Usage:
    .venv/Scripts/python.exe tools/train_proctoring_detector.py

Writes the best checkpoint to data/weights/proctoring_v1.pt. Does NOT
touch perception/object_detector.py's active weights — swapping it in is
a separate, deliberate step after tools/validate_proctoring_detector.py
confirms it's actually better than the stock detector on this project's
own real ground-truth footage, not just a training-loss curve.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ultralytics import YOLO

# The E: drive this project lives on was found completely full (98GB/98GB)
# partway through this session — downloading/training here risks corrupting
# other files if it fills the remaining sliver of space. Dataset and
# training runs live on C: (388GB free) instead; only the final, small
# best.pt checkpoint gets copied back into the repo's data/weights/.
DATASET_DIR = Path(r"C:\Users\jeeve\kinesis_training_data")
RUNS_DIR = Path(r"C:\Users\jeeve\kinesis_training_data\runs")
WEIGHTS_OUT = Path("data/weights/proctoring_v1.pt")


def find_data_yaml() -> Path:
    candidates = list(DATASET_DIR.rglob("data.yaml"))
    if not candidates:
        raise FileNotFoundError(f"No data.yaml found under {DATASET_DIR} — is the download finished?")
    return candidates[0]


def main() -> None:
    data_yaml = find_data_yaml()
    print(f"Training on {data_yaml}")

    model = YOLO("yolo11n.pt")
    results = model.train(
        data=str(data_yaml),
        epochs=40,
        patience=8,  # early-stop if val mAP stalls — real data, real overfitting risk at this size
        imgsz=640,
        batch=32,
        device="cuda",
        project=str(RUNS_DIR),
        name="proctoring_v1",
        exist_ok=True,
        verbose=True,
        # workers=0 (2026-08-23): default workers=8 spawns 8 subprocesses
        # that each re-import torch/cudnn — on this machine that blew past
        # the Windows page file's capacity ("paging file is too small") and
        # crashed the run entirely. Single-process data loading is slower
        # per epoch but doesn't touch the page file limit.
        workers=0,
    )
    best = Path(results.save_dir) / "weights" / "best.pt"
    WEIGHTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(best, WEIGHTS_OUT)
    print(f"Best checkpoint copied to {WEIGHTS_OUT}")
    print(f"Full training run (metrics, curves, val predictions) at {results.save_dir}")


if __name__ == "__main__":
    main()
