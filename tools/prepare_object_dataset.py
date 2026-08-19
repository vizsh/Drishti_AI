"""Merge downloaded Roboflow datasets into one YOLO-format dataset for the
phone detector fine-tune (docs/architecture.md §4).

Of the two datasets pulled by download_roboflow_datasets.py, only
exam-cheating-detector has object-level phone boxes ("Handphone"). The other
(exam-cheating) labels whole-scene students_cheating/students_not_cheating —
a behaviour-level label, not an object box, so it doesn't belong in the
object detector's training set; it's left as-is for the behaviour
classification stage to consider later instead.

Remaps Handphone -> class 0 "phone" and copies into a single merged dataset
directory with a matching data.yaml, ready for YOLO fine-tuning.

Usage:
    python -m tools.prepare_object_dataset
"""

from __future__ import annotations

import shutil
from pathlib import Path

SOURCE = Path("data/staged/roboflow_datasets/exam-cheating-detector")
TARGET = Path("data/staged/merged_object_dataset")
SOURCE_CLASSES = ["Handphone", "Memberi contekan", "Menengok", "Menunduk"]
KEEP_CLASS_NAME = "Handphone"
KEEP_CLASS_ID = SOURCE_CLASSES.index(KEEP_CLASS_NAME)
TARGET_CLASSES = ["phone"]


def remap_label_file(src_label: Path, dst_label: Path) -> bool:
    """Returns True if the output file has >=1 box (worth keeping)."""
    kept_lines = []
    for line in src_label.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        cls_id = int(parts[0])
        if cls_id == KEEP_CLASS_ID:
            kept_lines.append("0 " + " ".join(parts[1:]))  # remap to class 0 "phone"
    if kept_lines:
        dst_label.write_text("\n".join(kept_lines) + "\n")
        return True
    return False


def process_split(split: str) -> tuple[int, int]:
    src_images = SOURCE / split / "images"
    src_labels = SOURCE / split / "labels"
    dst_images = TARGET / split / "images"
    dst_labels = TARGET / split / "labels"
    dst_images.mkdir(parents=True, exist_ok=True)
    dst_labels.mkdir(parents=True, exist_ok=True)

    total, kept = 0, 0
    for label_path in src_labels.glob("*.txt"):
        total += 1
        image_candidates = list((SOURCE / split / "images").glob(label_path.stem + ".*"))
        if not image_candidates:
            continue
        image_path = image_candidates[0]

        dst_label_path = dst_labels / label_path.name
        if remap_label_file(label_path, dst_label_path):
            shutil.copy2(image_path, dst_images / image_path.name)
            kept += 1
        # images with no phone box are skipped for this phone-only detector;
        # they'd be needed again once paper/earpiece classes are added.
    return total, kept


def write_data_yaml() -> None:
    (TARGET / "data.yaml").write_text(
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n"
        f"nc: {len(TARGET_CLASSES)}\n"
        f"names: {TARGET_CLASSES}\n"
    )


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"{SOURCE} not found — run tools.download_roboflow_datasets first")

    for split in ["train", "valid", "test"]:
        total, kept = process_split(split)
        print(f"{split}: {kept}/{total} images had a phone box, kept")

    write_data_yaml()
    print(f"\nMerged dataset ready at {TARGET} (data.yaml written)")


if __name__ == "__main__":
    main()
