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
        remaining = list(self.cameras)
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
        )
        for cam in data["cameras"]
    ]
    return DeploymentConfig(
        expected_seats=data["expected_seats"],
        cameras=cameras,
        settling_seconds=data.get("settling_seconds", 20.0),
        object_detect_confidence=data.get("object_detect_confidence", 0.35),
    )
