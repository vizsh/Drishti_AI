"""Download the specific public Roboflow Universe datasets identified in
docs/architecture.md §4 for the phone/paper/earpiece object detector.

Deliberately a short, hand-picked list (not a broad Universe search-and-grab)
to stay conservative on a free-tier API key: three datasets matching the
architecture doc's dataset strategy, not everything available.

Usage:
    python -m tools.download_roboflow_datasets
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()

OUTPUT_DIR = Path("data/staged/roboflow_datasets")

# (workspace, project, version, why)
DATASETS = [
    ("online-exam-cheating-detection-kvdul", "cheating-faalb-jvigx-jxt99", 1,
     "~1798 images, person/phone/calculator classes"),
    ("kattal", "exam-cheating", 1,
     "~152 images, person/students_cheating/students_not_cheating"),
    ("erian-putra-assyakur-aseh8", "exam-cheating-detector", 1,
     "~313 images, Handphone class + pretrained baseline"),
]


def main() -> None:
    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        raise SystemExit("ROBOFLOW_API_KEY not set — check .env")

    rf = Roboflow(api_key=api_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for workspace, project_slug, version, note in DATASETS:
        target_dir = OUTPUT_DIR / project_slug
        if target_dir.exists() and any(target_dir.iterdir()):
            print(f"Skipping {project_slug} — already downloaded at {target_dir}")
            continue
        print(f"Downloading {workspace}/{project_slug} v{version} ({note})...")
        try:
            project = rf.workspace(workspace).project(project_slug)
            dataset = project.version(version).download("yolov8", location=str(target_dir))
            print(f"  -> {dataset.location}")
        except Exception as exc:  # noqa: BLE001 — report and continue to the next dataset
            print(f"  FAILED: {exc}")


if __name__ == "__main__":
    main()
