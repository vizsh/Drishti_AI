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
from calibration.multi_camera import SeatObservation, fuse_seat_observations
from backend.evidence import EVIDENCE_DIR, RollingFrameBuffer, estimate_head_bbox, save_evidence_clip
from ingestion.video_source import VideoSource
from perception.lighting import enhance_if_dark
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


def build_synthetic_second_camera_calibration() -> SeatCalibration:
    """A SIMULATED second camera for demonstrating multi-camera occlusion
    fusion (calibration/multi_camera.py, docs/architecture.md §8) live.

    This project has only one real camera's footage — there is no second
    physical camera. This calibration reuses the same video frames through
    a different homography (different image_points, same real seats) purely
    to exercise the fusion code path with real pose-confidence values, the
    same way build_illustrative_calibration() above is a hand-picked demo
    calibration rather than a measured one. It is NOT a second real view of
    the room, and is labeled as such everywhere it surfaces (SeatObservation
    .camera_id, the dashboard's system-info panel) — real multi-camera
    deployment requires genuine second-camera hardware and
    calibration/calibrate_tool.py run against its actual footage.
    """
    cal = SeatCalibration(
        camera_id="cam_b_SIMULATED",
        image_points=[(180, 210), (540, 270), (520, 160), (230, 120)],
        plane_points=[(0, 0), (400, 0), (400, 40), (0, 40)],
        max_snap_distance=60,
    )
    for seat_id, img_pt in {
        "seat_1": (280, 220),
        "seat_2": (360, 230),
    }.items():
        cal.seats[seat_id] = cal.project(img_pt)
    return cal


class SecondaryCameraFeed(threading.Thread):
    """Runs a second, independent pose pipeline against a SIMULATED second
    camera (see build_synthetic_second_camera_calibration) and publishes
    SeatObservations for the primary PipelineWorker to fuse. Deliberately
    minimal — no calibration/risk-engine duplication, just the raw
    per-frame observations fusion actually needs."""

    def __init__(self, video_path: str, device: Optional[str], target_fps: float = 10.0):
        super().__init__(daemon=True)
        self.seat_cal = build_synthetic_second_camera_calibration()
        self.pose_estimator = PoseEstimator(device=device)
        self.video_path = video_path
        self.target_fps = target_fps
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict[str, tuple[float, SeatObservation]] = {}
        self._prev_keypoints: dict[str, list[tuple[float, float]]] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def latest_observation(self, seat_id: str, now: float, max_age_s: float = 1.0) -> Optional[SeatObservation]:
        with self._lock:
            entry = self._latest.get(seat_id)
        if entry is None:
            return None
        ts, obs = entry
        return obs if (now - ts) <= max_age_s else None

    def run(self) -> None:
        while not self._stop_event.is_set():
            video = VideoSource(self.video_path, target_fps=self.target_fps)
            try:
                for frame in video.frames():
                    if self._stop_event.is_set():
                        break
                    sim_time = time.time()
                    poses = self.pose_estimator.estimate(frame.image, timestamp=sim_time)
                    for p in poses:
                        if p.track_id is None:
                            continue
                        x1, y1, x2, y2 = p.xyxy
                        seat_id, _ = self.seat_cal.nearest_seat(((x1 + x2) / 2.0, y2))
                        if seat_id is None:
                            continue
                        keypoints = p.smoothed_keypoints or p.keypoints
                        shoulder_width = abs(keypoints[RIGHT_SHOULDER][0] - keypoints[LEFT_SHOULDER][0]) or 1.0
                        motion = 0.0
                        if seat_id in self._prev_keypoints:
                            motion = compute_motion_magnitude(
                                self._prev_keypoints[seat_id], keypoints, p.keypoint_confidence, shoulder_width
                            )
                        self._prev_keypoints[seat_id] = keypoints
                        obs = SeatObservation(
                            camera_id=self.seat_cal.camera_id,
                            torso_yaw=p.torso_yaw_proxy(),
                            motion_magnitude=motion,
                            pose_confidence=p.detection_confidence(),
                        )
                        with self._lock:
                            self._latest[seat_id] = (sim_time, obs)
            finally:
                video.release()


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
        enable_simulated_second_camera: bool = True,
    ):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.event_queue = event_queue
        self.device = device
        self.target_fps = target_fps
        self.stream_every_n_frames = stream_every_n_frames
        self.object_detect_every_n_frames = object_detect_every_n_frames

        # Occlusion fusion (docs/architecture.md §8, PS risk "Occlusion") —
        # see build_synthetic_second_camera_calibration()'s docstring for why
        # this is a simulated second view, not real second-camera hardware.
        self.secondary_camera = SecondaryCameraFeed(video_path, device, target_fps) if enable_simulated_second_camera else None

        self.seat_cal = build_illustrative_calibration()
        self.calibrator = BaselineCalibrator(settling_window_seconds=settling_seconds)
        self.risk_engine = RiskEngine()
        self.gesture_detector = GestureDetector(self.seat_cal)
        self.pose_estimator = PoseEstimator(device=device)
        self.frame_buffer = RollingFrameBuffer(max_seconds=35.0)

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
        if self.secondary_camera is not None:
            self.secondary_camera.stop()

    def dismiss_alert(self, seat_id: str) -> None:
        """docs/architecture.md §10 feedback loop, wired to a real endpoint."""
        self.calibrator.widen_threshold(seat_id)
        self.event_queue.put(
            {"type": "feedback", "seat_id": seat_id, "message": f"{seat_id} baseline widened (false positive dismissed)"}
        )

    def run(self) -> None:
        self._start_wall_time = time.time()
        if self.secondary_camera is not None:
            self.secondary_camera.start()
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

                # Lighting robustness (docs/architecture.md §8, PS risk row
                # "Poor Lighting Conditions"): enhance only the copy fed to
                # the models, not what's stored/displayed — evidence clips
                # and the live feed should show what the camera actually
                # recorded, not a brightened misrepresentation of it.
                detect_input, was_enhanced = enhance_if_dark(frame.image)

                poses = self.pose_estimator.estimate(detect_input, timestamp=sim_time)
                # Every visible person's head, not just the alerting seat's —
                # genuine privacy compliance for the evidence clip requires
                # blurring everyone in frame.
                head_bboxes = [estimate_head_bbox(p) for p in poses]
                self.frame_buffer.add(sim_time, frame.image, [b for b in head_bboxes if b is not None])

                # Object detection (docs/architecture.md §4) runs on its own,
                # slower cadence — a separate model pass, not free.
                object_detections = []
                if self._frame_counter % self.object_detect_every_n_frames == 0:
                    object_detections = self.object_detector.detect(detect_input)

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

                    # Occlusion fusion: if the simulated second camera has a
                    # recent reading for this same seat, combine the two
                    # (confidence-weighted) before scoring — see
                    # calibration/multi_camera.py and this file's
                    # build_synthetic_second_camera_calibration().
                    primary_obs = SeatObservation(
                        camera_id=self.seat_cal.camera_id,
                        torso_yaw=p.torso_yaw_proxy(),
                        motion_magnitude=motion,
                        pose_confidence=p.detection_confidence(),
                    )
                    fused_cameras = [self.seat_cal.camera_id]
                    if self.secondary_camera is not None:
                        secondary_obs = self.secondary_camera.latest_observation(seat_id, sim_time)
                        if secondary_obs is not None:
                            fused = fuse_seat_observations([primary_obs, secondary_obs])
                            fused_cameras = fused.camera_id.split(",")
                        else:
                            fused = primary_obs
                    else:
                        fused = primary_obs

                    sample = TemporalSample(timestamp=sim_time, torso_yaw=fused.torso_yaw, motion_magnitude=fused.motion_magnitude)
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
                    detection_confidence = round(fused.pose_confidence, 2)
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
                            "confidence": detection_confidence,
                            "cameras": fused_cameras,
                        }
                    )
                    if assessment.explanation:
                        evidence_url = self._capture_evidence(seat_id, assessment.triggering_event)
                        self.event_queue.put(
                            {
                                "type": "alert",
                                "seat_id": seat_id,
                                "timestamp": sim_time,
                                "risk_score": round(assessment.risk_score, 3),
                                "explanation": assessment.explanation,
                                "object_label": object_label,
                                "confidence": detection_confidence,
                                "evidence_url": evidence_url,
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
                            "lighting_enhanced": was_enhanced,
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

    def _capture_evidence(self, seat_id: str, event) -> Optional[str]:
        """docs/architecture.md §9/§11: face-blurred evidence clip for a
        confirmed alert — the only raw-video artifact allowed to leave the
        edge boundary. Encoding runs on its own thread so it can't stall
        the live pipeline; the URL is returned immediately (deterministic
        filename) so the alert card can offer it right away."""
        if event is None:
            return None
        clip_frames = self.frame_buffer.extract(event.start_time, event.end_time)
        if not clip_frames:
            return None
        clip_id = f"{seat_id}_{int(event.start_time * 1000)}"
        clip_dir = EVIDENCE_DIR / clip_id
        threading.Thread(
            target=save_evidence_clip, args=(clip_frames, clip_dir, self.target_fps), daemon=True
        ).start()
        return f"/evidence/{clip_id}/manifest.json"
