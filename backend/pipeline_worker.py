"""Runs the real Stage 1-7 pipeline (ingestion -> pose -> seat-anchoring ->
baseline calibration -> risk engine) against real footage on a background
thread, pushing JSON-serializable events onto a thread-safe queue for the
FastAPI WebSocket layer to broadcast.

Not a data generator for the dashboard — this is the actual computer vision
pipeline from stages 1-7, running live. The dashboard shows what the system
really computes, not a scripted demo.
"""

from __future__ import annotations

import base64
import os
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

from behaviour.gestures import GestureDetector, explain_gesture
from calibration.baseline import BaselineCalibrator, TemporalSample, compute_motion_magnitude
from calibration.homography import SeatCalibration
from ingestion.video_source import VideoSource
from perception.object_detector import ObjectDetector
from perception.pose import LEFT_SHOULDER, RIGHT_SHOULDER, PoseEstimator
from risk_engine.scorer import RiskEngine

SKELETON_EDGES = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (0, 5), (0, 6),
]
RISK_COLOR_BGR = {"calm": (129, 209, 52), "elevated": (36, 191, 251), "alert": (91, 91, 251)}
FINE_TUNED_WEIGHTS = Path("data/weights/phone_detector_v1.pt")


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
        stream_every_n_frames: int = 2,
        object_detect_every_n_frames: int = 5,
    ):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.event_queue = event_queue
        self.device = device
        self.target_fps = target_fps
        self.stream_every_n_frames = stream_every_n_frames
        self.object_detect_every_n_frames = object_detect_every_n_frames

        self.seat_cal = build_illustrative_calibration()
        self.calibrator = BaselineCalibrator(settling_window_seconds=settling_seconds)
        self.risk_engine = RiskEngine()
        self.gesture_detector = GestureDetector(self.seat_cal)
        self.pose_estimator = PoseEstimator(device=device)

        # v1 fine-tune only, per docs/architecture.md §4 — known to overfit on
        # background objects (found via Stage 4 validation), so its output is
        # surfaced to the UI tagged "experimental", never fed silently as fact.
        weights = str(FINE_TUNED_WEIGHTS) if FINE_TUNED_WEIGHTS.exists() else "yolo11n.pt"
        self.object_detector = ObjectDetector(weights=weights, confidence_threshold=0.35, device=device)
        self.object_detector_is_finetuned = FINE_TUNED_WEIGHTS.exists()

        self._prev_keypoints: dict[str, list[tuple[float, float]]] = {}
        self._stop_event = threading.Event()
        self._start_wall_time = 0.0
        self._loop_count = 0
        self._frame_counter = 0
        self._last_frame_wall_time = 0.0

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
                self._frame_counter += 1
                poses = self.pose_estimator.estimate(frame.image, timestamp=sim_time)

                # Object detection (docs/architecture.md §4) runs on its own,
                # slower cadence — a separate model pass, not free.
                object_detections = []
                if self._frame_counter % self.object_detect_every_n_frames == 0:
                    object_detections = self.object_detector.detect(frame.image)

                vis = frame.image if self.stream_every_n_frames and self._frame_counter % self.stream_every_n_frames == 0 else None

                seen_seats = set()
                seat_risk_this_frame: dict[str, str] = {}

                for p in poses:
                    if p.track_id is None:
                        continue
                    x1, y1, x2, y2 = p.xyxy
                    anchor = ((x1 + x2) / 2.0, y2)
                    seat_id, dist = self.seat_cal.nearest_seat(anchor)
                    if seat_id is None:
                        continue
                    seen_seats.add(seat_id)

                    for gesture_event in self.gesture_detector.observe(seat_id, p, sim_time):
                        self.event_queue.put(
                            {
                                "type": "gesture_alert",
                                "seat_id": seat_id,
                                "timestamp": sim_time,
                                "gesture": gesture_event.gesture,
                                "explanation": explain_gesture(gesture_event),
                            }
                        )

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
                        seat_risk_this_frame[seat_id] = "calibrating"
                        if vis is not None:
                            self._draw_person(vis, p, seat_id, "calibrating", None)
                        continue

                    baseline = self.calibrator.baseline(seat_id)
                    yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
                    motion_z = baseline.motion_zscore(sample.motion_magnitude)

                    # nearest contraband detection to this seat's anchor, if any —
                    # tagged experimental in the UI, per the v1 overfitting finding.
                    object_label = None
                    object_conf = 0.0
                    for det in object_detections:
                        dx1, dy1, dx2, dy2 = det.xyxy
                        center = ((dx1 + dx2) / 2, (dy1 + dy2) / 2)
                        if self.seat_cal.nearest_seat(center)[0] == seat_id:
                            object_label, object_conf = det.label, det.confidence
                            break

                    assessment = self.risk_engine.observe(
                        seat_id=seat_id,
                        timestamp=sim_time,
                        yaw_zscore=yaw_z,
                        motion_zscore=motion_z,
                        baseline_yaw_mean=baseline.torso_yaw_mean,
                        baseline_yaw_std=baseline.torso_yaw_std,
                        object_label=object_label,
                        object_confidence=object_conf,
                    )

                    level = "alert" if assessment.risk_score >= 0.5 else ("elevated" if assessment.risk_score >= 0.25 else "calm")
                    seat_risk_this_frame[seat_id] = level
                    if vis is not None:
                        self._draw_person(vis, p, seat_id, level, assessment.risk_score)

                    self.event_queue.put(
                        {
                            "type": "telemetry",
                            "seat_id": seat_id,
                            "timestamp": sim_time,
                            "risk_score": round(assessment.risk_score, 3),
                            "yaw_z": round(yaw_z, 2) if yaw_z is not None else None,
                            "motion_z": round(motion_z, 2),
                            "object_label": object_label,
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
                                "object_label": object_label,
                            }
                        )

                for seat_id in list(self.seat_cal.seats.keys()):
                    if seat_id not in seen_seats:
                        self.event_queue.put({"type": "seat_empty", "seat_id": seat_id, "timestamp": sim_time})

                if vis is not None:
                    self._emit_frame(vis, sim_time)

                now = time.time()
                if now - self._last_frame_wall_time >= 1.0:
                    self._last_frame_wall_time = now
                    self.event_queue.put(
                        {
                            "type": "heartbeat",
                            "timestamp": sim_time,
                            "wall_time": now,
                            "object_detector_finetuned": self.object_detector_is_finetuned,
                        }
                    )
        finally:
            video.release()

    def _draw_person(self, vis, pose, seat_id: str, level: str, risk_score: Optional[float]) -> None:
        color = RISK_COLOR_BGR.get(level, (200, 200, 200))
        keypoints = pose.smoothed_keypoints or pose.keypoints
        for a, b in SKELETON_EDGES:
            if pose.keypoint_confidence[a] > 0.3 and pose.keypoint_confidence[b] > 0.3:
                xa, ya = keypoints[a]
                xb, yb = keypoints[b]
                cv2.line(vis, (int(xa), int(ya)), (int(xb), int(yb)), color, 2)
        x1, y1, x2, y2 = (int(v) for v in pose.xyxy)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
        label = seat_id.upper() if risk_score is None else f"{seat_id.upper()} {risk_score:.2f}"
        cv2.putText(vis, label, (x1, max(0, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    def _emit_frame(self, image, sim_time: float) -> None:
        small = cv2.resize(image, (480, int(image.shape[0] * 480 / image.shape[1])))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 65])
        if not ok:
            return
        b64 = base64.b64encode(buf).decode("ascii")
        self.event_queue.put({"type": "frame", "timestamp": sim_time, "image": b64})
