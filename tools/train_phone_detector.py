"""Fine-tune YOLO11n on the merged phone dataset (docs/architecture.md §4:
transfer learning from COCO weights, not from-scratch — the dataset is far
too small (69 train images) to train from zero without severe overfitting).

Usage: python -m tools.train_phone_detector

Note: must be guarded by __main__ — Windows uses spawn (not fork) for
multiprocessing, and an unguarded top-level model.train() call with
workers>0 causes every dataloader worker to re-import and re-execute this
whole module, which crashes. workers=0 sidesteps it entirely and is fine at
this dataset size.
"""

from ultralytics import YOLO


def main() -> None:
    model = YOLO("yolo11n.pt")
    model.train(
        data="data/staged/merged_object_dataset/data.yaml",
        epochs=80,
        imgsz=640,
        batch=8,
        device="cuda",
        workers=0,
        project="data/weights/runs",
        name="phone_detector_v1",
        patience=20,
        verbose=True,
    )


if __name__ == "__main__":
    main()
