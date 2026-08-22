"""Alert-quality inspection harness (2026-08-22 accuracy audit).

Runs the REAL pipeline (PipelineWorker._run_once, unmodified) against one
video file end-to-end, off the live server, and dumps every event it would
have emitted with timestamps -- so alert quality can be judged against
ground truth (these test videos have their real outcome in the filename:
"Candidate was found using a mobile phone", "Seat No. 12 was seen taking a
piece of paper") instead of guessed at.

Deliberately does not try to precisely calibrate seat positions for a video
whose real seating chart isn't known ahead of time -- it uses one wide
"seat_test" covering the whole occupied desk area, with a generous
max_snap_distance, so whoever is in frame anchors to it. That's wrong for
multi-seat separation but right for this question: does the detection
signal line up with the real events in the footage, at all.

Usage: .venv/Scripts/python.exe tools/inspect_video.py <video_path> [max_seconds]
"""

from __future__ import annotations

import json
import queue
import sys
import time
from pathlib import Path

from backend.deployment_config import CameraConfig
from backend.pipeline_worker import PipelineWorker
from calibration.homography import SeatCalibration


def build_camera_config(video_path: str, image_width: int, image_height: int) -> CameraConfig:
    w, h = image_width, image_height
    cal = SeatCalibration(
        camera_id="inspect_cam",
        image_points=[(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))],
        plane_points=[(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)],
        max_snap_distance=2000.0,
    )
    cal.seats["seat_test"] = (500.0, 500.0)
    return CameraConfig(
        camera_id="inspect_cam",
        video_path=video_path,
        image_width=w,
        image_height=h,
        calibration=cal,
        is_simulated=False,
    )


def main() -> None:
    video_path = sys.argv[1]
    max_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else None

    import cv2

    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    cap.release()

    cam = build_camera_config(video_path, w, h)
    eq: "queue.Queue" = queue.Queue()
    worker = PipelineWorker(
        cam,
        secondaries=[],
        event_queue=eq,
        settling_seconds=20.0,
        object_detect_confidence=0.20,
        device=None,
        target_fps=10.0,
        stream_frames=False,
    )
    worker._start_wall_time = time.time()

    events: list[dict] = []

    # Run _run_once() but bail out early if max_seconds is set, by monkeypatching
    # the stop condition via a wall-clock check inside a wrapper loop instead of
    # editing pipeline_worker.py itself.
    orig_put = eq.put

    def capturing_put(item, *a, **kw):
        if item.get("type") not in ("frame", "loop_start"):
            events.append(item)
        return orig_put(item, *a, **kw)

    eq.put = capturing_put  # type: ignore[assignment]

    start = time.time()
    print(f"Running real pipeline against: {video_path}", file=sys.stderr)
    print(f"Resolution: {w}x{h}", file=sys.stderr)

    if max_seconds:
        # Run in a background thread so we can time-box a long file.
        import threading

        t = threading.Thread(target=worker._run_once, daemon=True)
        t.start()
        t.join(timeout=max_seconds)
        worker._stop_event.set()
        t.join(timeout=5.0)
    else:
        worker._run_once()

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s wall time, {len(events)} non-frame events captured", file=sys.stderr)

    out_path = Path(video_path).with_suffix(".events.json")
    out_path = Path("data") / "inspection" / (Path(video_path).stem + ".events.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(events, indent=2, default=str))
    print(f"Wrote {out_path}", file=sys.stderr)

    # Human-readable summary to stdout
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print("\n=== Event counts ===")
    for t_, c in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"{t_:22s} {c}")

    print("\n=== Alerts (real, dispatchable) ===")
    for e in events:
        if e["type"] == "alert":
            print(f"t={e['timestamp']:.1f}s  risk={e.get('risk_score')}  obj={e.get('object_label')}  conf={e.get('confidence')}")
            print(f"    {e.get('explanation')}")

    print("\n=== Gesture alerts ===")
    for e in events:
        if e["type"] == "gesture_alert":
            print(f"t={e['timestamp']:.1f}s  {e.get('explanation')}")

    print("\n=== Calibration warnings ===")
    for e in events:
        if e["type"] == "calibration_warning":
            print(f"t={e['timestamp']:.1f}s  {e.get('explanation')}")

    print("\n=== Object detections seen in telemetry (any, incl. non-alert) ===")
    seen_objs = [(e["timestamp"], e["object_label"]) for e in events if e["type"] == "telemetry" and e.get("object_label")]
    for ts, label in seen_objs:
        print(f"t={ts:.1f}s  {label}")
    if not seen_objs:
        print("(none)")


if __name__ == "__main__":
    main()
