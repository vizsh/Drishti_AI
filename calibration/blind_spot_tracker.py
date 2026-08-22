"""Part 1a (2026-08-21): live, real-detection-based blind-spot analysis.

Distinct from calibration/coverage.py's static geometric check, which only
asks "does this seat's (x,y) fall inside this camera's homography-mapped
plane region" — a purely geometric question, answerable before a single
frame is ever decoded. This tracker instead watches actual seat
resolutions (PipelineWorker/SecondaryCameraFeed's real nearest_seat() hits
during a live pipeline run) over a short analysis window, so blind spots
caused by real-world occlusion — a monitor, another student, a doorframe —
that the static check structurally cannot see still show up. Run as a
distinct "live blind-spot analysis" result in the setup flow's summary
step, alongside (not replacing) /api/coverage.
"""

from __future__ import annotations

import threading
import time


class LiveBlindSpotTracker:
    def __init__(self, duration_seconds: float = 8.0):
        self.duration_seconds = duration_seconds
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._hits: dict[str, set[str]] = {}  # seat_id -> camera_ids that actually resolved a detection to it

    def record(self, camera_id: str, seat_id: str) -> None:
        with self._lock:
            self._hits.setdefault(seat_id, set()).add(camera_id)

    def elapsed(self) -> float:
        return time.time() - self._start_time

    def result(self, expected_seats: list[str], camera_ids: list[str]) -> dict:
        with self._lock:
            hits = {seat_id: sorted(cams) for seat_id, cams in self._hits.items()}

        seats_result = []
        for seat_id in sorted(set(expected_seats) | set(hits.keys())):
            cams = hits.get(seat_id, [])
            if len(cams) >= 2:
                status = "seen_by_both"
            elif len(cams) == 1:
                status = "seen_by_one"
            else:
                status = "blind_spot"
            seats_result.append({"seat_id": seat_id, "seen_by": cams, "status": status})

        return {
            "duration_seconds": self.duration_seconds,
            "cameras": camera_ids,
            "seats": seats_result,
            "blind_spot_count": sum(1 for s in seats_result if s["status"] == "blind_spot"),
            "single_camera_count": sum(1 for s in seats_result if s["status"] == "seen_by_one"),
            "dual_camera_count": sum(1 for s in seats_result if s["status"] == "seen_by_both"),
        }
