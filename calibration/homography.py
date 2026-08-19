"""Stage 3: seat-anchored identity via homography (docs/architecture.md §3).

Why this exists: Stage 2 (BoT-SORT) proved on real footage
(data/test_videos/04) that tracker IDs flicker/swap even across a short clip.
Attributing seat 12's history to seat 11 after an ID swap is the PS's own
named worst-case failure. Seat-anchoring sidesteps it: identity becomes
`seat_34`, not `track_187`, so a tracker ID swap after occlusion doesn't
matter — the seat re-anchors identity independent of tracker continuity.

The homography maps points from the camera image plane onto *some* real-world
planar surface, not necessarily the floor. Many CCTV angles over desks (this
project's own test footage included) show the desk plane, not the floor —
seated students' feet are occluded under the desk. cv2.findHomography doesn't
care which plane it is, as long as the correspondence points and the anchor
point taken per-detection are consistent with each other. This module anchors
on whichever plane the calibration points were picked from; by convention
that's the desk/seat surface for a seated exam-hall camera, using each
detection's lower bounding-box point as the per-frame anchor (closest visible
point to the seat), rather than a true foot-point when feet aren't visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

Point2D = Tuple[float, float]


@dataclass
class SeatCalibration:
    """One camera's mapping from image pixels to seat positions on a plane.

    `image_points` / `plane_points` are the >=4 correspondence points used to
    solve the homography (e.g. visible desk corners in the image, and their
    positions on the desk-plane in real-world or arbitrary consistent units).
    `seats` maps a seat_id to its known position on that same plane.
    """

    camera_id: str
    image_points: List[Point2D]
    plane_points: List[Point2D]
    seats: Dict[str, Point2D] = field(default_factory=dict)
    max_snap_distance: float = 50.0  # plane units; beyond this, no seat match

    def __post_init__(self) -> None:
        if len(self.image_points) < 4 or len(self.image_points) != len(self.plane_points):
            raise ValueError("Need >=4 image_points with a matching plane_points pair each")
        src = np.array(self.image_points, dtype=np.float32)
        dst = np.array(self.plane_points, dtype=np.float32)
        self._matrix, _ = cv2.findHomography(src, dst)
        if self._matrix is None:
            raise ValueError("cv2.findHomography failed to solve — check point correspondences")

    def project(self, image_point: Point2D) -> Point2D:
        """Image pixel -> plane coordinate."""
        pt = np.array([[image_point]], dtype=np.float32)  # shape (1,1,2)
        projected = cv2.perspectiveTransform(pt, self._matrix)
        x, y = projected[0, 0]
        return (float(x), float(y))

    def nearest_seat(self, image_point: Point2D) -> Tuple[Optional[str], float]:
        """Image pixel -> (seat_id, distance in plane units). seat_id is None
        if nothing is within max_snap_distance (e.g. a passing invigilator,
        not a seated student)."""
        plane_point = self.project(image_point)
        best_seat: Optional[str] = None
        best_dist = float("inf")
        for seat_id, seat_pos in self.seats.items():
            dist = float(np.hypot(plane_point[0] - seat_pos[0], plane_point[1] - seat_pos[1]))
            if dist < best_dist:
                best_dist = dist
                best_seat = seat_id
        if best_seat is None or best_dist > self.max_snap_distance:
            return None, best_dist
        return best_seat, best_dist

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(
                {
                    "camera_id": self.camera_id,
                    "image_points": self.image_points,
                    "plane_points": self.plane_points,
                    "seats": self.seats,
                    "max_snap_distance": self.max_snap_distance,
                },
                indent=2,
            )
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "SeatCalibration":
        data = json.loads(Path(path).read_text())
        return cls(
            camera_id=data["camera_id"],
            image_points=[tuple(p) for p in data["image_points"]],
            plane_points=[tuple(p) for p in data["plane_points"]],
            seats={k: tuple(v) for k, v in data["seats"].items()},
            max_snap_distance=data.get("max_snap_distance", 50.0),
        )
