"""Fine-tune YOLO11n on the merged phone dataset (docs/architecture.md §4:
transfer learning from COCO weights, not from-scratch — the dataset is far
too small (69 train images) to train from zero without severe overfitting).

Usage: python -m tools.train_phone_detector
"""
from ultralytics import YOLO

model = YOLO("yolo11n.pt")
model.train(
    data="data/staged/merged_object_dataset/data.yaml",
    epochs=80,
    imgsz=640,
    batch=8,
    device="cuda",
    project="data/weights/runs",
    name="phone_detector_v1",
    patience=20,
    verbose=False,
)
