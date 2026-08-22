"""Lab Setup room-scan (2026-08-22): the real data behind the "sensing
animation" — a short live window, scoped to ONE camera, that records every
real detection (bounding box + confidence) and resolves it to that
camera's own configured seats, exactly the way the live pipeline does it
every frame. The animation this feeds (frontend/src/components/
RoomScanOverlay.tsx) draws real boxes at real image coordinates with real
confidence numbers — this module is what makes that true rather than
decorative.

Deliberately distinct from calibration/blind_spot_tracker.py's
LiveBlindSpotTracker, which answers a cross-camera question ("does a
SECOND camera also see this seat") over an aggregate hit-count. This
answers a single-camera setup question ("what does THIS camera actually
see right now, and where, and how confidently") with per-detection
bounding boxes, which the blind-spot tracker never needed and doesn't
keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Bbox = tuple[float, float, float, float]


@dataclass
class _Hit:
    bbox: Bbox
    confidence: float
    timestamp: float


class RoomScanSession:
    def __init__(self, camera_id: str, duration_seconds: float = 5.0):
        self.camera_id = camera_id
        self.duration_seconds = duration_seconds
        self._hits: dict[str, list[_Hit]] = {}

    def record(self, camera_id: str, seat_id: str, bbox: Bbox, confidence: float, timestamp: float) -> None:
        if camera_id != self.camera_id:
            return
        self._hits.setdefault(seat_id, []).append(_Hit(bbox=bbox, confidence=confidence, timestamp=timestamp))

    def result(self, expected_seats: dict[str, Bbox]) -> dict:
        """expected_seats: seat_id -> that seat's calibrated image position
        (a small bbox around calibration/coverage.py's project_inverse()
        point), used as the placeholder box position for a seat that got
        ZERO real detections this scan -- so even the "we never saw this
        seat" case has a real, calibration-derived image location to draw
        at, not an arbitrary one."""
        seats_out = []
        for seat_id, fallback_bbox in expected_seats.items():
            hits = self._hits.get(seat_id, [])
            if not hits:
                seats_out.append(
                    {
                        "seat_id": seat_id,
                        "status": "occluded",
                        "confidence": 0.0,
                        "bbox": list(fallback_bbox),
                        "hit_count": 0,
                    }
                )
                continue
            avg_conf = sum(h.confidence for h in hits) / len(hits)
            best = max(hits, key=lambda h: h.confidence)
            # >=3 hits over the scan window is the same "seen more than
            # once, not a fluke" bar risk_engine/object_persistence.py
            # already uses elsewhere in this project for exactly the same
            # reason -- a single lucky frame shouldn't count as "visible."
            if len(hits) >= 3 and avg_conf >= 0.6:
                status = "visible"
            else:
                status = "partial"
            seats_out.append(
                {
                    "seat_id": seat_id,
                    "status": status,
                    "confidence": round(avg_conf, 2),
                    "bbox": list(best.bbox),
                    "hit_count": len(hits),
                }
            )

        covered = sum(1 for s in seats_out if s["status"] != "occluded")
        coverage_pct = round(100 * covered / len(seats_out)) if seats_out else 0
        return {
            "camera_id": self.camera_id,
            "duration_seconds": self.duration_seconds,
            "seats": seats_out,
            "coverage_pct": coverage_pct,
            "visible_count": sum(1 for s in seats_out if s["status"] == "visible"),
            "partial_count": sum(1 for s in seats_out if s["status"] == "partial"),
            "occluded_count": sum(1 for s in seats_out if s["status"] == "occluded"),
        }
