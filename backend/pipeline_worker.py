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
from typing import Callable, Optional

import cv2

from behaviour.gestures import GestureDetector, explain_gesture
from calibration.baseline import BaselineCalibrator, TemporalSample, compute_motion_magnitude
from calibration.multi_camera import SeatObservation, fuse_seat_observations
from backend.deployment_config import CameraConfig
from backend.evidence import EVIDENCE_DIR, RollingFrameBuffer, estimate_head_bbox, save_evidence_clip
from calibration.quality import SeatAnchorQualityTracker
from calibration.compute_budget import SeatComputeBudget
from ingestion.video_source import VideoSource
from perception.lighting import enhance_if_dark
from perception.motion_heatmap import MotionHeatmapAccumulator
from perception.object_detector import ObjectDetector
from perception.roi_contraband import detect_in_roi, workspace_roi
from perception.pose import LEFT_SHOULDER, RIGHT_SHOULDER, PoseEstimator
from risk_engine.object_persistence import ObjectPersistenceTracker
from risk_engine.scorer import RiskEngine

SKELETON_EDGES = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (0, 5), (0, 6),
]
RISK_COLOR_BGR = {"calm": (129, 209, 52), "elevated": (36, 191, 251), "alert": (91, 91, 251)}
FINE_TUNED_WEIGHTS = Path("data/weights/phone_detector_v1.pt")
# Dashboard grid (2026-08-22): a "background" camera's frames are sampled
# far more sparsely than a "focused" one — a grid tile only needs an
# occasional thumbnail, not a smooth feed, and this is what keeps
# multiple cameras streaming at once cheap.
BACKGROUND_STREAM_EVERY_N_FRAMES = 20
# Accuracy audit (2026-08-22): which detected LABELS are trustworthy enough
# to stand as an alert's sole corroboration -- a per-class distinction, not
# a per-model one (see risk_engine/adjudication.py's object_class_verified
# docstring). "cell phone" is a mature, heavily-validated stock COCO class,
# confirmed against real ground-truth footage this session. "book"
# (perception/object_detector.py's own comment) is an explicitly
# unvalidated placeholder proxy for paper/chit and stays untrusted alone.
VERIFIED_OBJECT_LABELS = {"cell phone"}


class SecondaryCameraFeed(threading.Thread):
    """Runs a second, independent pose pipeline against a camera config
    (config/deployment.json, loaded via backend/deployment_config.py) and
    publishes SeatObservations for the primary PipelineWorker to fuse.
    Deliberately minimal — no calibration/risk-engine duplication, just the
    raw per-frame observations fusion actually needs. If camera_config
    .is_simulated is True (see config/deployment.json's comment on
    cam_b_SIMULATED), this camera is reusing the primary's own footage
    through a different calibration purely to exercise the fusion code
    path — real multi-camera deployment configures a genuine second
    camera's video_path here instead."""

    def __init__(
        self,
        camera_config: CameraConfig,
        device: Optional[str],
        target_fps: float = 10.0,
        on_seat_observed: Optional[Callable[[str, str], None]] = None,
        on_seat_detection: Optional[Callable[[str, str, tuple, float, float], None]] = None,
    ):
        super().__init__(daemon=True)
        self.seat_cal = camera_config.calibration
        self.pose_estimator = PoseEstimator(device=device)
        self._video_playlist = camera_config.playlist
        self._playlist_index = 0
        self.video_path = self._video_playlist[self._playlist_index]
        self.image_width = camera_config.image_width
        self.image_height = camera_config.image_height
        self.target_fps = target_fps
        # Part 1a: fires on every real (non-None) nearest_seat() resolution
        # so a live blind-spot analysis window can observe actual detection
        # coverage, not just the static homography geometry check.
        self.on_seat_observed = on_seat_observed
        # Lab Setup room-scan (2026-08-22): same firing point as
        # on_seat_observed above, but carries the actual bbox/confidence a
        # RoomScanSession needs to draw a real wireframe box, not just
        # "this seat was hit."
        self.on_seat_detection = on_seat_detection
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
                        if self.on_seat_observed is not None:
                            self.on_seat_observed(self.seat_cal.camera_id, seat_id)
                        if self.on_seat_detection is not None:
                            self.on_seat_detection(self.seat_cal.camera_id, seat_id, p.xyxy, p.detection_confidence(), sim_time)
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
                            torso_yaw=p.hybrid_torso_yaw(self.image_width, self.image_height),
                            motion_magnitude=motion,
                            pose_confidence=p.detection_confidence(),
                        )
                        with self._lock:
                            self._latest[seat_id] = (sim_time, obs)
            finally:
                video.release()
            # Accuracy audit (2026-08-22): same playlist-cycling as
            # PipelineWorker.run() -- see CameraConfig.playlist.
            self._playlist_index = (self._playlist_index + 1) % len(self._video_playlist)
            self.video_path = self._video_playlist[self._playlist_index]


class PipelineWorker(threading.Thread):
    def __init__(
        self,
        primary: CameraConfig,
        secondaries: list[CameraConfig],
        event_queue: "queue.Queue",
        settling_seconds: float = 20.0,
        object_detect_confidence: float = 0.35,
        device: Optional[str] = None,
        target_fps: float = 10.0,
        stream_every_n_frames: int = 2,
        # Accuracy audit (2026-08-22): raised from 1-in-5 to 1-in-2 sampled
        # frames after finding a real contraband object visible only in
        # brief, occlusion-interrupted windows (a candidate's own body
        # blocking the camera's view of her hands most of the time) --
        # checking every ~0.5s missed those windows outright; every ~0.2s
        # catches enough of them to corroborate via ObjectPersistenceTracker.
        object_detect_every_n_frames: int = 2,
        stream_frames: bool = True,
        on_seat_observed: Optional[Callable[[str, str], None]] = None,
        on_seat_detection: Optional[Callable[[str, str, tuple, float, float], None]] = None,
    ):
        super().__init__(daemon=True)
        self.camera_id = primary.camera_id
        # Part 1a: same live blind-spot-analysis hook as SecondaryCameraFeed,
        # fired from this worker's own primary-camera seat resolutions below.
        self.on_seat_observed = on_seat_observed
        self.on_seat_detection = on_seat_detection
        # Accuracy audit (2026-08-22): video_path stays the CURRENT file
        # (used by every existing call site below unchanged); the
        # playlist cycles it forward in run(), once per full pass through
        # a file, instead of _run_once() reopening the same path forever.
        # See CameraConfig.playlist's docstring for why this exists.
        self._video_playlist = primary.playlist
        self._playlist_index = 0
        self.video_path = self._video_playlist[self._playlist_index]
        self.image_width = primary.image_width
        self.image_height = primary.image_height
        self.event_queue = event_queue
        self.device = device
        self.target_fps = target_fps
        self.stream_every_n_frames = stream_every_n_frames
        self.object_detect_every_n_frames = object_detect_every_n_frames
        # Dashboard accuracy audit (2026-08-22): used to be a fixed
        # constructor flag with only one worker ever set to stream_frames
        # =True, permanently blanking every other camera tile. Replaced
        # with a live-settable three-level mode so every camera can
        # actually be viewed, not just the first one:
        #   "off"       — no frame decode/emit at all (cheapest).
        #   "background"— a low-rate thumbnail (every
        #                  BACKGROUND_STREAM_EVERY_N_FRAMES-th qualifying
        #                  frame) — enough for a grid tile, not a full feed.
        #   "focused"   — full rate (stream_every_n_frames), for whichever
        #                  single tile the user actually opened — the
        #                  original "never decode more than one full feed
        #                  at a time" performance rule still holds, it's
        #                  just enforced by mode instead of by construction.
        self.stream_mode = "focused" if stream_frames else "background"

        # Occlusion fusion (docs/architecture.md §8, PS risk "Occlusion") —
        # one SecondaryCameraFeed per camera that shares >=1 seat with this
        # group's primary (backend/deployment_config.py's worker_groups()).
        # See config/deployment.json's cam_b_SIMULATED comment for why the
        # demo config's second camera is simulated, not real hardware.
        self.secondary_cameras = [
            SecondaryCameraFeed(cam, device, target_fps, on_seat_observed=on_seat_observed, on_seat_detection=on_seat_detection)
            for cam in secondaries
        ]

        self.seat_cal = primary.calibration
        self.calibrator = BaselineCalibrator(settling_window_seconds=settling_seconds)
        self.risk_engine = RiskEngine()
        self.gesture_detector = GestureDetector(self.seat_cal)
        self.anchor_quality = SeatAnchorQualityTracker(camera_id=self.camera_id)
        self.compute_budget = SeatComputeBudget(base_interval_frames=object_detect_every_n_frames)
        # Accuracy audit (2026-08-22): a real phone in real footage
        # (data/test_videos/01) was confirmed present by this ROI detector
        # at confidence up to 0.36, but sat in a noisy 0.10-0.33 band most
        # of the time -- below the old single-frame 0.30-0.35 bar, so the
        # real signal was being thrown away. This requires the SAME label
        # twice within a window instead of trusting one frame, so the
        # confidence floor can come down without letting a one-off false
        # positive through on its own. Window widened to 4.5s (not 3.0)
        # because the object is only briefly visible between moments the
        # candidate's own body occludes it from this camera's angle --
        # confirmed by dumping the actual ROI crops used frame-by-frame
        # around the real incident: most show her back, a minority show a
        # hand/object at the desk. Two occluded-then-visible glimpses
        # further apart still need to corroborate each other.
        self.object_persistence = ObjectPersistenceTracker(window_seconds=4.5, min_hits=2)
        self.pose_estimator = PoseEstimator(device=device)
        self.frame_buffer = RollingFrameBuffer(max_seconds=35.0)
        self.heatmap: Optional[MotionHeatmapAccumulator] = None  # lazily sized on first frame
        self._last_raw_frame = None

        # Accuracy audit (2026-08-22): this used to auto-switch to
        # FINE_TUNED_WEIGHTS whenever the file existed on disk, with no
        # check that its class taxonomy even matched what gets requested.
        # It doesn't: data/weights/phone_detector_v1.pt is a single-class
        # model (YOLO('...').names == {0: 'phone'}), but ObjectDetector's
        # default `classes` filter asks for COCO indices 67 ("cell phone")
        # and 73 ("book") -- indices that don't exist in this model's
        # 1-class output space. Every request for class 67/73 against a
        # model that only ever predicts class 0 returns nothing, silently,
        # every single frame. Confirmed directly: running the real
        # pipeline against ground-truth footage of a candidate actually
        # using a phone (data/test_videos/01) produced zero object
        # detections of any kind, for the entire video, every time --
        # not a threshold problem, this model was never able to detect
        # anything through this filter. Combined with docs/build_order.md's
        # own finding that v1 additionally overfit and false-positived on a
        # static chair (69 training images, since documented as too few),
        # the fine-tuned checkpoint is not used until a validated,
        # correctly-labeled v2 exists — stock COCO yolo11n.pt is used
        # instead, which DOES genuinely detect a real phone in that same
        # ground-truth footage (confirmed up to 0.36 confidence, directly
        # against the real incident window).
        self.object_detector = ObjectDetector(
            weights="yolo11n.pt", confidence_threshold=object_detect_confidence, device=device
        )
        self.object_detector_is_finetuned = False

        self._prev_keypoints: dict[str, list[tuple[float, float]]] = {}
        self._stop_event = threading.Event()
        self._start_wall_time = 0.0
        self._loop_count = 0
        self._frame_counter = 0
        self._last_frame_wall_time = 0.0

        # Part 2b: defense-side counter-evidence state, per seat — a
        # recent false-alarm dismissal or a recent calibration-issue
        # signature both feed risk_engine.adjudicate() so an alert relying
        # solely on a signal this seat is known to be unreliable about
        # gets vetoed rather than dispatched.
        self._false_alarm_counts: dict[str, int] = {}
        self._last_calibration_warning: dict[str, float] = {}
        self._calibration_warning_window_s = 120.0

        # Accuracy audit (2026-08-22): a seat that's genuinely, repeatedly
        # doing the same thing (checking a phone every 15-20s for the
        # whole exam, confirmed against real ground-truth footage,
        # data/test_videos/02) is real evidence every time -- but pushing
        # 14 separate toast/audio notifications across one session for the
        # same ongoing pattern is exactly the alert fatigue this whole
        # audit exists to fix. Every alert still gets logged/persisted and
        # shown in the Alerts list regardless; this only gates the
        # interrupt-worthy "notify" flag the frontend uses for toast/audio,
        # so a recurring pattern reads as "seat_X: Nth occurrence this
        # session" instead of N separate pop-ups.
        self._last_notify_time: dict[str, float] = {}
        self._seat_alert_counts: dict[str, int] = {}
        self._notify_cooldown_s = 60.0

    def stop(self) -> None:
        self._stop_event.set()
        for cam in self.secondary_cameras:
            cam.stop()

    def set_stream_mode(self, mode: str) -> None:
        """Dashboard grid (2026-08-22): live-settable, not fixed at
        construction — lets the frontend put a camera into "background"
        (grid thumbnail) or "focused" (full-rate single view) mode on
        demand, and drop it back to "off" when nobody's looking at it."""
        if mode not in ("off", "background", "focused"):
            raise ValueError(f"invalid stream mode: {mode!r}")
        self.stream_mode = mode

    def dismiss_alert(self, seat_id: str) -> None:
        """docs/architecture.md §10 feedback loop, wired to a real endpoint.
        Kept as a thin alias for resolve_alert's "false_alarm" case — the
        endpoint that used to call this directly still can."""
        self.resolve_alert(seat_id, "false_alarm")

    def resolve_alert(self, seat_id: str, resolution: str, invigilator: Optional[str] = None) -> None:
        """Phase 4: dispatch/resolution audit trail, extending the existing
        dismiss-as-feedback mechanism rather than adding a second, disconnected
        one. Only "false_alarm" widens this seat's baseline threshold — that's
        the one resolution that means the alert shouldn't have fired, which is
        the actual signal the calibrator's feedback loop exists to consume
        (docs/architecture.md §10). "confirmed"/"no_action" are logged for the
        audit trail (same event_queue -> db.log_events path as every other
        event) without touching calibration, since the alert was correct."""
        if resolution == "false_alarm":
            self.calibrator.widen_threshold(seat_id)
            self._false_alarm_counts[seat_id] = self._false_alarm_counts.get(seat_id, 0) + 1
            message = f"{seat_id} baseline widened (false positive dismissed)"
        elif resolution == "confirmed":
            message = f"{seat_id} alert confirmed by invigilator"
        else:
            message = f"{seat_id} resolved — no action taken"
        self.event_queue.put(
            {
                "type": "feedback",
                "seat_id": seat_id,
                "message": message,
                "resolution": resolution,
                "invigilator": invigilator,
            }
        )

    def acknowledge_alert(self, seat_id: str, invigilator: str) -> None:
        """Part 6 (invigilator ergonomics, 2026-08-21): a lightweight "seen,
        noted" action distinct from dispatch/resolve — for a minor item that
        doesn't warrant a full dispatch-and-resolution cycle. Deliberately
        does NOT touch calibration (unlike a false_alarm resolution) and
        doesn't require a resolution taxonomy pick — it's just an audited
        "an invigilator looked at this" marker, and the alert stays open for
        a later dispatch/resolve if it turns out to need one."""
        self.event_queue.put(
            {
                "type": "acknowledge",
                "seat_id": seat_id,
                "message": f"{invigilator} acknowledged alert at {seat_id}",
                "invigilator": invigilator,
            }
        )

    def dispatch_invigilator(self, seat_id: str, invigilator: str) -> None:
        """Phase 4: logs a dispatch action (who, when) as its own audited
        event — separate from resolution since a dispatch can precede its
        resolution by however long the invigilator takes to walk over."""
        self.event_queue.put(
            {
                "type": "dispatch",
                "seat_id": seat_id,
                "message": f"{invigilator} dispatched to {seat_id}",
                "invigilator": invigilator,
            }
        )

    def seat_baseline(self, seat_id: str) -> Optional[dict]:
        """Part 2.6: the raw personal-baseline numbers behind the Digital
        Twin view — this seat's own settling-window mean/std, the actual
        basis every z-score for this seat is measured against. None until
        this seat's calibration completes."""
        baseline = self.calibrator.baseline(seat_id)
        if baseline is None:
            return None
        return {
            "torso_yaw_mean": round(baseline.torso_yaw_mean, 3),
            "torso_yaw_std": round(baseline.torso_yaw_std, 3),
            "motion_mean": round(baseline.motion_mean, 3),
            "motion_std": round(baseline.motion_std, 3),
        }

    def calibration_quality(self) -> dict:
        """Part 2.5: live seat-anchor hit-rate signal for this camera —
        surfaced on the Pre-Exam Coverage panel alongside the static
        geometric coverage check, since a bad calibration only shows up
        once real detections are flowing through it."""
        q = self.anchor_quality.snapshot()
        return {"camera_id": q.camera_id, "hit_rate": q.hit_rate, "sample_count": q.sample_count, "status": q.status}

    def _alerting_enabled(self) -> bool:
        """Part A (2026-08-21 pre-demo hardening): a camera whose seat-
        anchor calibration is flagged needs_attention (Part 2.5) keeps
        showing real-time risk/telemetry for monitoring, but must not
        generate actionable alerts — a hit rate this low means most
        "detections" that do land on a seat are more likely coincidental
        than a genuinely tracked student, and an alert built on that isn't
        trustworthy enough to dispatch an invigilator over."""
        return self.anchor_quality.snapshot().status != "needs_attention"

    def render_heatmap_jpeg(self) -> Optional[bytes]:
        """Current session motion heatmap as JPEG bytes, or None before the
        first frame has been processed."""
        if self.heatmap is None or self._last_raw_frame is None:
            return None
        overlay = self.heatmap.render(base_image=self._last_raw_frame)
        ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return buf.tobytes() if ok else None

    def run(self) -> None:
        self._start_wall_time = time.time()
        for cam in self.secondary_cameras:
            cam.start()
        while not self._stop_event.is_set():
            self._loop_count += 1
            self.event_queue.put({"type": "loop_start", "loop": self._loop_count, "video_path": self.video_path})
            self._run_once()
            # Accuracy audit (2026-08-22): advance to the NEXT file in the
            # playlist once this one ends, wrapping back to the start only
            # after a full pass -- a single file no longer just loops
            # itself forever (see CameraConfig.playlist). A live (RTSP)
            # source's frames() never returns except via stop_event, so
            # this line is unreachable for that case, same as before.
            self._playlist_index = (self._playlist_index + 1) % len(self._video_playlist)
            self.video_path = self._video_playlist[self._playlist_index]

    def _run_once(self) -> None:
        video = VideoSource(self.video_path, target_fps=self.target_fps)
        try:
            for frame in video.frames():
                if self._stop_event.is_set():
                    break
                sim_time = time.time() - self._start_wall_time  # monotonic clock for calibration/risk logic
                self._frame_counter += 1

                # Session motion heatmap (perception/motion_heatmap.py) — a
                # PS #2-style output computed as a free byproduct of frames
                # this pipeline already decodes, not a second processing pass.
                if self.heatmap is None:
                    self.heatmap = MotionHeatmapAccumulator(frame.image.shape[:2])
                self.heatmap.update(frame.image)
                self._last_raw_frame = frame.image

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

                # Per-seat bbox/keypoints for THIS frame, keyed by seat_id —
                # Phase 3's annotated-evidence overlay needs the alerting
                # seat's box/skeleton at each frame of the clip, not just the
                # text explanation. Computed here (cheap nearest_seat lookup,
                # duplicated below in the scoring loop) so it can ride along
                # with frame_buffer.add() before seat assignment happens for
                # scoring purposes.
                seat_poses: dict[str, dict] = {}
                for p in poses:
                    if p.track_id is None:
                        continue
                    x1, y1, x2, y2 = p.xyxy
                    seat_id, _ = self.seat_cal.nearest_seat(((x1 + x2) / 2.0, y2))
                    if seat_id is None:
                        continue
                    keypoints = p.smoothed_keypoints or p.keypoints
                    seat_poses[seat_id] = {
                        "xyxy": [round(v, 1) for v in p.xyxy],
                        "keypoints": [[round(x, 1), round(y, 1)] for x, y in keypoints],
                        "keypoint_confidence": [round(c, 2) for c in p.keypoint_confidence],
                    }

                self.frame_buffer.add(sim_time, frame.image, [b for b in head_bboxes if b is not None], seat_poses)

                # Object detection (docs/architecture.md §4) runs on its own,
                # slower cadence — a separate model pass, not free. Phase 2b
                # (2026-08-21): cropped to each tracked person's workspace
                # region (shoulders/elbows/wrists) rather than the full
                # frame — measured on real footage to cut phone_detector_v1's
                # documented false-positive rate (docs/build_order.md: fired
                # on a static chair) from 100% to 61% of frames. Not a full
                # fix (some desks/partitions still trigger within a
                # student's own crop), so this stays tagged "experimental"
                # in the UI exactly as before, just measurably better.
                # Phase 2c (2026-08-21): per-seat adaptive cadence — a seat
                # sustained-calm for 10+ minutes checks far less often, a
                # seat that isn't drops back to full rate immediately. Only
                # applies to this per-person ROI check (see
                # calibration/compute_budget.py's docstring for why the
                # shared full-frame pose pass above can't do the same).
                object_detections: list = []
                for p in poses:
                    if p.track_id is None:
                        continue
                    ox1, oy1, ox2, oy2 = p.xyxy
                    obj_seat_id, _ = self.seat_cal.nearest_seat(((ox1 + ox2) / 2.0, oy2))
                    if obj_seat_id is None:
                        continue
                    interval = self.compute_budget.object_detect_interval(obj_seat_id, sim_time)
                    if self._frame_counter % interval != 0:
                        continue
                    roi = workspace_roi(p, self.image_width, self.image_height)
                    if roi is not None:
                        object_detections.extend(detect_in_roi(self.object_detector, detect_input, roi))

                if self.stream_mode == "focused":
                    stream_interval = self.stream_every_n_frames
                elif self.stream_mode == "background":
                    stream_interval = BACKGROUND_STREAM_EVERY_N_FRAMES
                else:
                    stream_interval = 0
                vis = (
                    frame.image
                    if stream_interval and self._frame_counter % stream_interval == 0
                    else None
                )

                seen_seats = set()
                seat_risk_this_frame: dict[str, str] = {}

                for p in poses:
                    if p.track_id is None:
                        continue
                    x1, y1, x2, y2 = p.xyxy
                    anchor = ((x1 + x2) / 2.0, y2)
                    seat_id, dist = self.seat_cal.nearest_seat(anchor)
                    self.anchor_quality.record(hit=seat_id is not None)
                    if seat_id is None:
                        continue
                    seen_seats.add(seat_id)
                    if self.on_seat_observed is not None:
                        self.on_seat_observed(self.camera_id, seat_id)
                    if self.on_seat_detection is not None:
                        self.on_seat_detection(self.camera_id, seat_id, p.xyxy, p.detection_confidence(), sim_time)

                    # Phase 1 (2026-08-21 gap fix): whether a genuine (not
                    # calibration-issue) gesture completed for this seat this
                    # frame — fed into risk_engine.observe() below so
                    # risk_score/seat-card color actually reflect it, not
                    # just the alert feed. A calibration_warning-flagged
                    # gesture must NOT raise risk — that's the whole point
                    # of Part 2.5 distinguishing it from a genuine incident.
                    gesture_active = False
                    for gesture_event in self.gesture_detector.observe(seat_id, p, sim_time):
                        if gesture_event.likely_calibration_issue:
                            # Part 2.5 (2026-08-21) pushed this to the live
                            # alert feed as a distinct event type. Accuracy
                            # audit (2026-08-22): that made it a NOTIFICATION
                            # in its own right, which is backwards -- this
                            # signal exists specifically to say "this is
                            # NOT a real incident, don't treat it as one,"
                            # and a rough illustrative calibration can throw
                            # this repeatedly enough to flood the invigilator
                            # feed with exactly the noise it was meant to
                            # suppress. It still updates
                            # _last_calibration_warning (used as a real
                            # defense signal in risk_engine's adjudication —
                            # see recent_calibration_warning below) and is
                            # still visible via the Calibration Quality
                            # panel's own pull-based per-camera hit-rate
                            # check, but no longer pushed as a live
                            # push-notification event.
                            self._last_calibration_warning[seat_id] = sim_time
                        else:
                            gesture_active = True
                            # Part A (2026-08-21 pre-demo hardening): still
                            # feeds risk_score/monitoring via gesture_active
                            # above regardless - only the actionable event
                            # (alert feed / evidence / dispatch) is gated.
                            if self._alerting_enabled():
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

                    # Occlusion fusion: combine this seat's reading with any
                    # recent reading from other configured cameras
                    # (confidence-weighted) before scoring — see
                    # calibration/multi_camera.py and config/deployment.json.
                    primary_obs = SeatObservation(
                        camera_id=self.seat_cal.camera_id,
                        torso_yaw=p.hybrid_torso_yaw(self.image_width, self.image_height),
                        motion_magnitude=motion,
                        pose_confidence=p.detection_confidence(),
                    )
                    observations = [primary_obs]
                    for cam in self.secondary_cameras:
                        secondary_obs = cam.latest_observation(seat_id, sim_time)
                        if secondary_obs is not None:
                            observations.append(secondary_obs)
                    fused = fuse_seat_observations(observations)
                    fused_cameras = fused.camera_id.split(",")

                    sample = TemporalSample(timestamp=sim_time, torso_yaw=fused.torso_yaw, motion_magnitude=fused.motion_magnitude)
                    self.calibrator.observe(seat_id, sample)

                    if not self.calibrator.is_calibrated(seat_id):
                        progress = self.calibrator.calibration_progress(seat_id, sim_time)
                        self.event_queue.put(
                            {"type": "calibrating", "seat_id": seat_id, "progress": progress, "timestamp": sim_time}
                        )
                        seat_risk_this_frame[seat_id] = "calibrating"
                        self.compute_budget.observe(seat_id, sim_time, "calibrating")
                        if vis is not None:
                            self._draw_person(vis, p, seat_id, "calibrating", None)
                        continue

                    baseline = self.calibrator.baseline(seat_id)
                    yaw_z = baseline.yaw_zscore(sample.torso_yaw) if sample.torso_yaw is not None else None
                    motion_z = baseline.motion_zscore(sample.motion_magnitude)

                    # nearest contraband detection to this seat's anchor, if any —
                    # tagged experimental in the UI, per the v1 overfitting finding.
                    raw_object_label = None
                    raw_object_conf = 0.0
                    raw_object_center = None
                    for det in object_detections:
                        dx1, dy1, dx2, dy2 = det.xyxy
                        center = ((dx1 + dx2) / 2, (dy1 + dy2) / 2)
                        if self.seat_cal.nearest_seat(center)[0] == seat_id:
                            raw_object_label, raw_object_conf = det.label, det.confidence
                            raw_object_center = center
                            break

                    # Confirmed = seen at least twice within 3s AND not
                    # sitting suspiciously still for a long stretch (see
                    # ObjectPersistenceTracker's docstring — a real ROI
                    # crop of a real desk fixture, e.g. a bottle, false-
                    # positived as "cell phone" throughout an entire real
                    # video and this is what catches it). Not the raw
                    # per-frame hit, is what scoring/alerting/telemetry
                    # actually use, so a single noisy frame can't fire an
                    # alert and a genuine object isn't thrown away just
                    # because one frame's confidence dipped.
                    confirmed = self.object_persistence.observe(
                        seat_id, sim_time, raw_object_label, raw_object_conf, raw_object_center
                    )
                    object_label = confirmed.label if confirmed else None
                    object_conf = confirmed.confidence if confirmed else 0.0
                    object_duration = confirmed.duration if confirmed else 0.0

                    detection_confidence = round(fused.pose_confidence, 2)
                    camera_needs_attention = self.anchor_quality.snapshot().status == "needs_attention"
                    recent_calibration_warning = (
                        sim_time - self._last_calibration_warning.get(seat_id, -1e9) < self._calibration_warning_window_s
                    )
                    assessment = self.risk_engine.observe(
                        seat_id=seat_id,
                        timestamp=sim_time,
                        yaw_zscore=yaw_z,
                        motion_zscore=motion_z,
                        baseline_yaw_mean=baseline.torso_yaw_mean,
                        baseline_yaw_std=baseline.torso_yaw_std,
                        object_label=object_label,
                        object_confidence=object_conf,
                        object_duration=object_duration,
                        gesture_active=gesture_active,
                        object_class_verified=object_label in VERIFIED_OBJECT_LABELS,
                        fused_confidence=fused.pose_confidence,
                        camera_needs_attention=camera_needs_attention,
                        recent_false_alarm_count=self._false_alarm_counts.get(seat_id, 0),
                        recent_calibration_warning=recent_calibration_warning,
                    )

                    level = "alert" if assessment.risk_score >= 0.5 else ("elevated" if assessment.risk_score >= 0.25 else "calm")
                    seat_risk_this_frame[seat_id] = level
                    self.compute_budget.observe(seat_id, sim_time, level)
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
                    if assessment.explanation and assessment.is_alert and self._alerting_enabled():
                        evidence_url = self._capture_evidence(seat_id, assessment.triggering_event)
                        self._seat_alert_counts[seat_id] = self._seat_alert_counts.get(seat_id, 0) + 1
                        last_notify = self._last_notify_time.get(seat_id, -1e9)
                        # Accuracy audit (2026-08-22): a needs_verification
                        # alert (moderate-confidence object detection with
                        # zero other corroboration -- the stock detector's
                        # real false-positive band, confirmed against real
                        # footage) never auto-notifies, cooldown or not; it's
                        # still logged/visible for a human to check.
                        notify = (
                            not assessment.needs_verification
                            and (sim_time - last_notify) >= self._notify_cooldown_s
                        )
                        if notify:
                            self._last_notify_time[seat_id] = sim_time
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
                                # Part 2b: the deterministic prosecution/defense
                                # checklist behind this alert - shown to the
                                # invigilator as an inspectable list, not
                                # hidden reasoning.
                                "prosecution": [f.__dict__ for f in assessment.prosecution],
                                "defense": [f.__dict__ for f in assessment.defense],
                                # Accuracy audit (2026-08-22): every alert is
                                # still logged/persisted, but only a
                                # "notify"=true one should interrupt the
                                # invigilator (toast/audio) -- a recurring
                                # pattern for the same seat within
                                # _notify_cooldown_s reads as an occurrence
                                # count instead of a fresh pop-up each time.
                                "notify": notify,
                                "occurrence": self._seat_alert_counts[seat_id],
                                "needs_verification": assessment.needs_verification,
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
                            "camera_id": self.camera_id,
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
        # Dashboard grid (2026-08-22): a "background"-mode frame is a grid
        # thumbnail, not a full feed — smaller resize, more compression,
        # since it's rendered small and infrequently. "focused" keeps the
        # original size/quality for the one tile actually being watched.
        if self.stream_mode == "background":
            width, quality = 240, 55
        else:
            width, quality = 480, 65
        small = cv2.resize(image, (width, int(image.shape[0] * width / image.shape[1])))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return
        b64 = base64.b64encode(buf).decode("ascii")
        # camera_id tag (2026-08-22): previously only one worker ever
        # streamed at all, so "frame" events were implicitly single-source.
        # Now that multiple workers can stream at once, every frame event
        # must say which camera it's from so the frontend can route it to
        # the right tile instead of overwriting one global image.
        self.event_queue.put({"type": "frame", "camera_id": self.camera_id, "timestamp": sim_time, "image": b64})

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
            target=save_evidence_clip, args=(clip_frames, clip_dir, self.target_fps, seat_id), daemon=True
        ).start()
        return f"/evidence/{clip_id}/manifest.json"
