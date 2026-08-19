"""Upload the 405 candidate frames (extracted by
tools/extract_candidate_frames.py from real footage) to a Roboflow project
for labeling — needed because the v1 phone detector (docs/architecture.md
§4, trained on public data only) was found to false-positive on background
objects (a chair) rather than real phones; own-domain labeled data is the fix.

Uses the raw REST upload endpoint directly rather than the roboflow SDK's
Project.upload(): the SDK's workspace.project() call to fetch project
metadata 404s for this API key/workspace even for a project that
demonstrably exists (confirmed via workspace.projects()) — a Roboflow-side
quirk, not something fixable here. The plain upload endpoint works fine and
is all this script needs.

Usage:
    python -m tools.upload_to_roboflow            # uploads all candidate frames
    python -m tools.upload_to_roboflow --limit 5   # test run
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from roboflow import Roboflow

load_dotenv()

PROJECT_SLUG = "kinesis-ai-contraband"
CANDIDATE_FRAMES_DIR = Path("data/staged/candidate_frames")
UPLOAD_URL = f"https://api.roboflow.com/dataset/{PROJECT_SLUG}/upload"


def ensure_project_exists(api_key: str) -> None:
    rf = Roboflow(api_key=api_key)
    workspace = rf.workspace()
    existing_ids = workspace.projects()  # e.g. ["idibag/kinesis-ai-contraband", ...]
    if any(pid.endswith(f"/{PROJECT_SLUG}") for pid in existing_ids):
        print(f"Project '{PROJECT_SLUG}' already exists")
        return
    print(f"Creating project '{PROJECT_SLUG}'...")
    workspace.create_project(
        project_name=PROJECT_SLUG,
        project_type="object-detection",
        project_license="MIT",
        annotation="phone",
    )
    time.sleep(3)


def upload_image(api_key: str, image_path: Path, retries: int = 3) -> tuple[bool, str]:
    last_error = ""
    for attempt in range(retries):
        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    UPLOAD_URL,
                    params={"api_key": api_key, "name": image_path.name},
                    files={"file": (image_path.name, f, "image/jpeg")},
                    timeout=60,
                )
            if resp.status_code == 200:
                return True, resp.json().get("id", "")
            last_error = resp.text[:200]
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
        time.sleep(2 * (attempt + 1))  # backoff before retry
    return False, last_error


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Upload only the first N frames (test run)")
    args = parser.parse_args()

    api_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        raise SystemExit("ROBOFLOW_API_KEY not set — check .env")

    ensure_project_exists(api_key)

    images = sorted(CANDIDATE_FRAMES_DIR.rglob("*.jpg"))
    if args.limit:
        images = images[: args.limit]
    print(f"Uploading {len(images)} candidate frames...")

    uploaded, failed = 0, 0
    for i, img_path in enumerate(images):
        ok, info = upload_image(api_key, img_path)
        if ok:
            uploaded += 1
        else:
            failed += 1
            print(f"  FAILED {img_path.name}: {info}")
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(images)} processed ({uploaded} ok, {failed} failed)")
            time.sleep(1)  # gentle pacing, stay well under free-tier rate limits

    print(f"\nDone: {uploaded} uploaded, {failed} failed.")
    print(f"Label them at https://app.roboflow.com/idibag/{PROJECT_SLUG}")


if __name__ == "__main__":
    main()
