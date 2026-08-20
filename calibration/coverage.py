"""Pre-exam camera coverage validator (docs/architecture.md §13,
differentiator #10): automatically check every seat in the institution's
seating chart falls within at least one camera's field of view *before*
the exam starts, using the same homography already validated in Stage 3 —
turning "camera blind spots" (named in the PS's own risk table) from a
risk discovered mid-exam into one pre-empted at setup time.

A seat can fail coverage two distinct ways, and the validator says which:
1. It isn't in any camera's calibration at all (calibrate_tool.py was
   never run for it, or the seating chart changed since calibration).
2. It IS calibrated, but its position projects outside that camera's real
   image frame (or too close to the edge to be reliable) — catches a stale
   or drifted calibration, not just a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from calibration.homography import Point2D, SeatCalibration


def image_point_in_bounds(image_point: Point2D, image_width: int, image_height: int, edge_margin_px: float = 0.0) -> bool:
    x, y = image_point
    return edge_margin_px <= x <= image_width - edge_margin_px and edge_margin_px <= y <= image_height - edge_margin_px


@dataclass
class CameraCoverageInput:
    camera_id: str
    calibration: SeatCalibration
    image_width: int
    image_height: int
    edge_margin_px: float = 20.0  # a seat right at the frame edge is unreliable in practice


@dataclass
class SeatCoverageResult:
    seat_id: str
    covered: bool
    covering_cameras: list[str]
    reason: Optional[str] = None  # populated when covered is False


def validate_coverage(expected_seat_ids: list[str], cameras: list[CameraCoverageInput]) -> list[SeatCoverageResult]:
    results: list[SeatCoverageResult] = []
    for seat_id in expected_seat_ids:
        covering: list[str] = []
        failure_reasons: list[str] = []

        for cam in cameras:
            if seat_id not in cam.calibration.seats:
                continue
            plane_point = cam.calibration.seats[seat_id]
            image_point = cam.calibration.project_inverse(plane_point)
            if image_point_in_bounds(image_point, cam.image_width, cam.image_height, cam.edge_margin_px):
                covering.append(cam.camera_id)
            else:
                x, y = image_point
                failure_reasons.append(f"{cam.camera_id}: calibrated but projects to ({x:.0f},{y:.0f}), outside usable frame")

        if covering:
            results.append(SeatCoverageResult(seat_id=seat_id, covered=True, covering_cameras=covering))
        else:
            reason = "; ".join(failure_reasons) if failure_reasons else "not present in any camera's calibration"
            results.append(SeatCoverageResult(seat_id=seat_id, covered=False, covering_cameras=[], reason=reason))

    return results
