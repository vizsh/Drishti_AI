"""Phase 2c (2026-08-21): adaptive compute budgeting per seat.

Scoped honestly to what the current architecture actually allows: one
VideoSource decodes one shared frame per camera, and one full-frame
YOLO11-pose pass tracks every visible person in it simultaneously — there
is no way to run pose/tracking at a genuinely different fps for one seat
vs another within that single pass without breaking seat-anchoring's
frame-to-frame keypoint continuity for everyone else in the same frame.
So this does NOT scale the whole pipeline's fps per seat (that would need
per-seat independent crops fed through separate trackers - a much larger
architectural change, and one that risks the exact tracking-continuity
problem seat-anchoring exists to solve).

What CAN safely vary per seat: the object-detection ROI check added in
Phase 2b (perception/roi_contraband.py) is already a per-person loop, one
model call per tracked person, independent of the others. This tracks how
long each seat has been calm and scales that seat's object-check interval
down when sustained-calm, back up to full rate the moment risk rises -
real, seat-independent compute savings on the one stage of the pipeline
where that's actually safe to do.
"""

from __future__ import annotations


class SeatComputeBudget:
    def __init__(
        self,
        base_interval_frames: int = 5,
        calm_interval_frames: int = 30,
        sustained_calm_seconds: float = 600.0,
    ):
        self.base_interval_frames = base_interval_frames
        self.calm_interval_frames = calm_interval_frames
        self.sustained_calm_seconds = sustained_calm_seconds
        # seat_id -> sim_time this seat was last seen NOT calm (elevated/
        # critical, or not yet calibrated). Absent = calm since first seen.
        self._last_non_calm_time: dict[str, float] = {}
        self._first_seen_time: dict[str, float] = {}

    def observe(self, seat_id: str, timestamp: float, level: str) -> None:
        """Call once per frame per seat with that frame's risk level
        ("calm"/"watch"/"critical"/"calibrating")."""
        self._first_seen_time.setdefault(seat_id, timestamp)
        if level != "calm":
            self._last_non_calm_time[seat_id] = timestamp

    def calm_duration(self, seat_id: str, timestamp: float) -> float:
        since = self._last_non_calm_time.get(seat_id, self._first_seen_time.get(seat_id, timestamp))
        return max(0.0, timestamp - since)

    def object_detect_interval(self, seat_id: str, timestamp: float) -> int:
        """Frames between object-detector ROI checks for this seat right
        now. Full rate (base_interval_frames) for a seat that isn't
        sustained-calm; a much sparser check once it's been calm long
        enough that a contraband check is unlikely to matter, dropping
        back to full rate immediately once risk rises again."""
        if self.calm_duration(seat_id, timestamp) >= self.sustained_calm_seconds:
            return self.calm_interval_frames
        return self.base_interval_frames
