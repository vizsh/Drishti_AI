"""Runs the real Stage 1-7 pipeline (ingestion -> pose -> seat-anchoring ->
baseline calibration -> risk engine) against real footage on a background
thread, pushing JSON-serializable events onto a thread-safe queue for the
FastAPI WebSocket layer to broadcast.

Not a data generator for the dashboard — this is the actual computer vision
pipeline from stages 1-7, running live. The dashboard shows what the system
really computes, not a scripted demo.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

from calibration.baseline import BaselineCalibrator, TemporalSample, compute_motion_magnitude
from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.pose import LEFT_SHOULDER, RIGHT_SHOULDER, PoseEstimator
from risk_engine.scorer import RiskEngine


def build_illustrative_calibration() -> SeatCalibration:
    """Same hand-picked demo calibration validated in Stage 3/6/7 — not
    accurate real-world measurements, just enough seats to exercise the
    full pipeline live. Real deployment uses calibration/calibrate_tool.py."""
    cal = SeatCalibration(
        camera_id="cam04_illustrative",
        image_points=[(200, 195), (560, 260), (560, 150), (245, 105)],
        plane_points=[(0, 0), (400, 0), (400, 40), (0, 40)],
        max_snap_distance=60,
    )
    for seat_id, img_pt in {
        "seat_1": (290, 210),
        "seat_2": (370, 220),
        "seat_3": (470, 230),
        "seat_4": (550, 240),
    }.items():
        cal.seats[seat_id] = cal.project(img_pt)
    return cal


class PipelineWorker(threading.Thread):
    def __init__(
        self,
        video_path: str,
        event_queue: "queue.Queue",
        device: Optional[str] = None,
        settling_seconds: float = 20.0,
        target_fps: float = 10.0,
    ):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.event_queue = event_queue
        self.device = device
        self.target_fps = target_fps

        self.seat_cal = build_illustrative_calibration()
        self.calibrator = BaselineCalibrator(settling_window_seconds=settling_seconds)
        self.risk_engine = RiskEngine()
        self.pose_estimator = PoseEstimator(device=device)
        self._prev_keypoints: dict[str, list[tuple[float, float]]] = {}
        self._stop_event = threading.Event()
        self._start_wall_time = 0.0
        self._loop_count = 0

    def stop(self) -> None:
        self._stop_event.set()

    def dismiss_alert(self, seat_id: str) -> None:
        """docs/architecture.md §10 feedback loop, wired to a real endpoint."""
        self.calibrator.widen_threshold(seat_id)
        self.event_queue.put(
            {"type": "feedback", "seat_id": seat_id, "message": f"{seat_id} baseline widened (false positive dismissed)"}
        )

    def run(self) -> None:
        self._start_wall_time = time.time()
        while not self._stop_event.is_set():
            self._loop_count += 1
            self.event_queue.put({"type": "loop_start", "loop": self._loop_count})
            self._run_once()

    def _run_once(self) -> None:
        video = VideoSource(self.video_path, target_fps=self.target_fps)
        try:
            for frame in video.frames():
                if self._stop_event.is_set():
                    break
                sim_time = time.time() - self._start_wall_time  # monotonic clock for calibration/risk logic
                poses = self.pose_estimator.estimate(frame.image, timestamp=sim_time)

                seen_seats = set()
                for p in poses:
                    if p.track_id is None:
                        continue
                    x1, y1, x2, y2 = p.xyxy
                    anchor = ((x1 + x2) / 2.0, y2)
                    seat_id, dist = self.seat_cal.nearest_seat(anchor)
                    if seat_id is None:
                        continue
                    seen_seats.add(seat_id)

                    keypoints = p.smoothed_keypoints or p.keypoints
                    shoulder_width = abs(keypoints[RIGHT_SHOULDER][0] - keypoints[LEFT_SHOULDER][0]) or 1.0
                    motion = 0.0
                    if seat_id in self._prev_keypoints:
                        motion = compute_motion_magnitude(
                            self._prev_keypoints[seat_id], keypoints, p.keypoint_confidence, shoulder_width
                        )
                    self._prev_keypoints[seat_id] = keypoints

                    sample = TemporalSample(timestamp=sim_time, torso_yaw=p.torso_yaw_proxy(), motion_magnitude=motion)
                    self.calibrator.observe(seat_id, sample)

                    if not self.calibrator.is_calibrated(seat_id):
                        progress = self.calibrator.calibration_progress(seat_id, sim_time)
                        self.event_queue.put(
                            {"type": "calibrating", "seat_id": seat_id, "progress": progress, "timestamp": sim_time}
                        )
                        continue

                    baseline = self.calibrator.baseline(seat_id)
                    yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
                    motion_z = baseline.motion_zscore(sample.motion_magnitude)

                    assessment = self.risk_engine.observe(
                        seat_id=seat_id,
                        timestamp=sim_time,
                        yaw_zscore=yaw_z,
                        motion_zscore=motion_z,
                        baseline_yaw_mean=baseline.torso_yaw_mean,
                        baseline_yaw_std=baseline.torso_yaw_std,
                        object_label=None,
                    )

                    self.event_queue.put(
                        {
                            "type": "telemetry",
                            "seat_id": seat_id,
                            "timestamp": sim_time,
                            "risk_score": round(assessment.risk_score, 3),
                            "yaw_z": round(yaw_z, 2) if yaw_z is not None else None,
                            "motion_z": round(motion_z, 2),
                        }
                    )
                    if assessment.explanation:
                        self.event_queue.put(
                            {
                                "type": "alert",
                                "seat_id": seat_id,
                                "timestamp": sim_time,
                                "risk_score": round(assessment.risk_score, 3),
                                "explanation": assessment.explanation,
                            }
                        )

                for seat_id in list(self.seat_cal.seats.keys()):
                    if seat_id not in seen_seats:
                        self.event_queue.put({"type": "seat_empty", "seat_id": seat_id, "timestamp": sim_time})
        finally:
            video.release()
