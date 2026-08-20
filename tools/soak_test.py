"""Part 0.5 soak test: runs the real PipelineWorker continuously against the
simulated RTSP stream (real-time paced, looped video), sampling process
memory, GPU memory, and event-queue/DB growth every 60s. Writes a CSV so the
trend is reviewable without keeping this process's stdout around.

Not part of the permanent codebase — a one-off audit script.
"""
from __future__ import annotations

import csv
import os
import queue
import sys
import time
from pathlib import Path

import psutil
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).parent.parent))

# Separate DB file so this soak test doesn't pollute the real demo database
# or collide session_ids with whatever backend/main.py instance is running.
_soak_db_path = Path(__file__).parent / "soak_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_soak_db_path.as_posix()}"

from backend import db
from backend.deployment_config import CameraConfig
from backend.pipeline_worker import PipelineWorker
from calibration.homography import SeatCalibration

try:
    import torch
    HAS_CUDA = torch.cuda.is_available()
except ImportError:
    HAS_CUDA = False

cal = SeatCalibration(
    camera_id="soak_test_cam",
    image_points=[(200, 195), (560, 260), (560, 150), (245, 105)],
    plane_points=[(0, 0), (400, 0), (400, 40), (0, 40)],
    max_snap_distance=60.0,
)
cal.seats = {
    "seat_1": cal.project((290, 210)),
    "seat_2": cal.project((370, 220)),
    "seat_3": cal.project((470, 230)),
    "seat_4": cal.project((550, 240)),
}
cam = CameraConfig(
    camera_id="soak_test_cam", video_path="rtsp://127.0.0.1:8554/kinesis_test",
    image_width=640, image_height=480, calibration=cal, is_simulated=False,
)

db.init_db()
session_id = db.create_session(cam.video_path)

event_queue: "queue.Queue" = queue.Queue()
worker = PipelineWorker(cam, [], event_queue, settling_seconds=20.0, device="cuda" if HAS_CUDA else None, stream_frames=False)
worker.start()

proc = psutil.Process()
out_path = Path(__file__).parent / "soak_test_results.csv"
event_counts: dict[str, int] = {}
db_batch: list[dict] = []

with out_path.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["elapsed_s", "rss_mb", "gpu_mb", "frames_processed", "loop_count", "queue_depth", "db_row_count", "db_size_mb", "event_counts"])
    f.flush()

    t0 = time.time()
    last_sample = 0.0
    while True:
        try:
            ev = event_queue.get(timeout=1.0)
            event_counts[ev["type"]] = event_counts.get(ev["type"], 0) + 1
            db_batch.append(ev)
            if len(db_batch) >= 50:
                db.log_events(session_id, db_batch)
                db_batch = []
        except queue.Empty:
            pass

        elapsed = time.time() - t0
        if elapsed - last_sample >= 60.0:
            last_sample = elapsed
            if db_batch:
                db.log_events(session_id, db_batch)
                db_batch = []
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            gpu_mb = 0.0
            if HAS_CUDA:
                import torch
                gpu_mb = torch.cuda.memory_allocated() / (1024 * 1024)
            with db.SessionLocal() as dbs:
                row_count = dbs.execute(select(func.count()).select_from(db.EventLog)).scalar() or 0
            db_size_mb = db.DB_PATH.stat().st_size / (1024 * 1024) if db.DB_PATH.exists() else 0.0
            writer.writerow([
                round(elapsed, 1), round(rss_mb, 1), round(gpu_mb, 1),
                worker._frame_counter, worker._loop_count, event_queue.qsize(),
                row_count, round(db_size_mb, 2), dict(event_counts),
            ])
            f.flush()
            print(f"[t={elapsed/60:.1f}min] rss={rss_mb:.0f}MB gpu={gpu_mb:.0f}MB frames={worker._frame_counter} events={dict(event_counts)}", flush=True)
