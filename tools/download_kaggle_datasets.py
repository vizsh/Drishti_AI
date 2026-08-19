"""Download hand-picked public Kaggle datasets matching docs/architecture.md
§4's dataset strategy. Short, specific list — not a broad search-and-grab.

Usage:
    python -m tools.download_kaggle_datasets
"""

from __future__ import annotations

from pathlib import Path

import kaggle

OUTPUT_DIR = Path("data/staged/kaggle_datasets")

DATASET_REFS = [
    "aneelapervez/classroom-exam-cheating-detection",
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for ref in DATASET_REFS:
        target_dir = OUTPUT_DIR / ref.split("/")[-1]
        if target_dir.exists() and any(target_dir.iterdir()):
            print(f"Skipping {ref} — already downloaded at {target_dir}")
            continue
        print(f"Downloading {ref}...")
        kaggle.api.dataset_download_files(ref, path=str(target_dir), unzip=True)
        print(f"  -> {target_dir}")


if __name__ == "__main__":
    main()
