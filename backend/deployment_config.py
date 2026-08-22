"""Loads deployment configuration from config/deployment.json —
externalizes camera calibration, seating chart, and pipeline settings that
were previously hardcoded across backend/pipeline_worker.py and
backend/main.py. Closes PS #1's "Generalization Across Institutions"
requirement (updated PDF, item 12): "adaptable and configurable for
deployment across multiple educational environments." Deploying to a new
room means editing config/deployment.json, not the codebase — no code
change needed to add a camera, move a seat, or point at a different video
source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from calibration.homography import SeatCalibration

DEFAULT_CONFIG_PATH = Path("config/deployment.json")


@dataclass
class CameraConfig:
    camera_id: str
    video_path: str
    image_width: int
    image_height: int
    calibration: SeatCalibration
    is_simulated: bool = False
    hall: str = "Hall A"
    # Accuracy audit (2026-08-22): a single video file used to loop forever
    # (PipelineWorker._run_once() re-opens the same video_path every time
    # it ends), which is exactly why the same handful of behaviours kept
    # re-triggering alerts session after session in testing — it was
    # replaying the identical footage, not simulating a longer exam. When
    # set, video_paths lets one camera cycle through multiple files in
    # sequence (one full pass through the list, then repeats from the
    # start) instead of looping a single clip — see
    # backend/pipeline_worker.py's playlist handling. Empty means "use
    # video_path alone," so existing single-file configs need no changes.
    video_paths: list[str] = field(default_factory=list)
    # Accuracy audit (2026-08-22): lets a camera be taken out of the live
    # deployment without editing/removing its config entry — worker_groups()
    # below filters these out entirely, so a disconnected camera runs no
    # pipeline, streams no frames, and produces no seats/alerts until
    # reconnected. See POST /api/setup/cameras/{id}/disconnect|reconnect.
    disconnected: bool = False

    @property
    def playlist(self) -> list[str]:
        return self.video_paths if self.video_paths else [self.video_path]


@dataclass
class DeploymentConfig:
    expected_seats: list[str]
    cameras: list[CameraConfig]
    settling_seconds: float = 20.0
    object_detect_confidence: float = 0.35

    @property
    def primary_camera(self) -> CameraConfig:
        return self.cameras[0]

    @property
    def secondary_cameras(self) -> list[CameraConfig]:
        return self.cameras[1:]

    def worker_groups(self) -> list[tuple[CameraConfig, list[CameraConfig]]]:
        """Groups cameras into independent (primary, [secondaries]) pairs by
        actual seat overlap, not by a flat "camera 0 is primary" assumption.

        Found via a real bug: seats covered ONLY by a "secondary" camera that
        shares no seats with any primary never got scored at all — a
        SecondaryCameraFeed only ever feeds fusion for seats its paired
        primary already calibrates/scores in its own main loop (backend/
        pipeline_worker.py). A camera with zero seat overlap with anything
        already grouped needs its own independent primary worker, or its
        seats are structurally invisible to the system. This groups
        first-by-arrival, chaining any camera that shares >=1 seat with an
        existing group's primary into that group as a fusion secondary, and
        starting a new group otherwise.
        """
        groups: list[tuple[CameraConfig, list[CameraConfig]]] = []
        # Accuracy audit (2026-08-22): a disconnected camera gets no
        # worker at all — not started, not scored, not streamed — until
        # reconnected. See CameraConfig.disconnected's docstring.
        remaining = [cam for cam in self.cameras if not cam.disconnected]
        while remaining:
            primary = remaining.pop(0)
            primary_seats = set(primary.calibration.seats.keys())
            secondaries: list[CameraConfig] = []
            still_remaining: list[CameraConfig] = []
            for cam in remaining:
                if set(cam.calibration.seats.keys()) & primary_seats:
                    secondaries.append(cam)
                else:
                    still_remaining.append(cam)
            groups.append((primary, secondaries))
            remaining = still_remaining
        return groups


def _build_calibration(cam: dict) -> SeatCalibration:
    cal = SeatCalibration(
        camera_id=cam["camera_id"],
        image_points=[tuple(p) for p in cam["image_points"]],
        plane_points=[tuple(p) for p in cam["plane_points"]],
        max_snap_distance=cam.get("max_snap_distance", 60.0),
    )
    for seat_id, img_pt in cam["seats"].items():
        cal.seats[seat_id] = cal.project(tuple(img_pt))
    return cal


def save_hall_cameras(hall: str, cameras: list[dict], path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Part F (multi-camera lab setup, 2026-08-21): merges a hall's camera
    list into config/deployment.json — replaces any existing cameras
    already assigned to this hall, leaves every other hall's cameras
    untouched. Each dict in `cameras` must match the same schema
    load_deployment_config() reads (camera_id, video_path, image_width/
    height, image_points, plane_points, seats, ...). Newly-referenced seat
    ids are appended to expected_seats so the coverage check picks them up.
    """
    data = json.loads(path.read_text())
    halls = data.setdefault("halls", {})
    other_halls_cameras = [c for c in data["cameras"] if halls.get(c["camera_id"]) != hall]
    data["cameras"] = other_halls_cameras + cameras
    for cam in cameras:
        halls[cam["camera_id"]] = hall
        for seat_id in cam["seats"]:
            if seat_id not in data["expected_seats"]:
                data["expected_seats"].append(seat_id)
    path.write_text(json.dumps(data, indent=2))


def set_camera_disconnected(camera_id: str, disconnected: bool, path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """Accuracy audit (2026-08-22): flips one camera's disconnected flag in
    config/deployment.json in place, leaving everything else untouched.
    Returns False if camera_id isn't in the config (caller should 404),
    True on success. Pairs with worker_groups() filtering disconnected
    cameras out entirely on the next _start_workers() call."""
    data = json.loads(path.read_text())
    found = False
    for cam in data["cameras"]:
        if cam["camera_id"] == camera_id:
            cam["disconnected"] = disconnected
            found = True
            break
    if found:
        path.write_text(json.dumps(data, indent=2))
    return found


def load_deployment_config(path: Path = DEFAULT_CONFIG_PATH) -> DeploymentConfig:
    data = json.loads(path.read_text())
    halls = data.get("halls", {})
    cameras = [
        CameraConfig(
            camera_id=cam["camera_id"],
            video_path=cam["video_path"],
            image_width=cam["image_width"],
            image_height=cam["image_height"],
            calibration=_build_calibration(cam),
            is_simulated=cam.get("is_simulated", False),
            hall=halls.get(cam["camera_id"], "Hall A"),
            video_paths=cam.get("video_paths", []),
            disconnected=cam.get("disconnected", False),
        )
        for cam in data["cameras"]
    ]
    return DeploymentConfig(
        expected_seats=data["expected_seats"],
        cameras=cameras,
        settling_seconds=data.get("settling_seconds", 20.0),
        object_detect_confidence=data.get("object_detect_confidence", 0.35),
    )
