"""Stage 7: temporal pattern scoring (docs/architecture.md §7).

Isolated-event alerting causes invigilator alert fatigue. "3 head turns
toward the same neighbor within 2 minutes" is a different risk category
than "1 six-second glance" — real cheating is repetitive by nature, a
single glance rarely is.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Deque

from risk_engine.events import DeviationEvent


class EventPatternTracker:
    def __init__(self, window_seconds: float = 300.0):
        self.window_seconds = window_seconds
        self._events: dict[str, Deque[DeviationEvent]] = {}

    def add(self, event: DeviationEvent) -> None:
        seat_events = self._events.setdefault(event.seat_id, deque())
        seat_events.append(event)
        cutoff = event.end_time - self.window_seconds
        while seat_events and seat_events[0].end_time < cutoff:
            seat_events.popleft()

    def event_count(self, seat_id: str, now: float) -> int:
        seat_events = self._events.get(seat_id, deque())
        cutoff = now - self.window_seconds
        return sum(1 for e in seat_events if e.end_time >= cutoff)

    def pattern_score(self, seat_id: str, now: float) -> float:
        """Roughly saturating: 1 event is low, 3+ events in the window is
        high. sqrt dampens growth so it doesn't scale unbounded/linearly."""
        count = self.event_count(seat_id, now)
        return math.sqrt(count) if count > 0 else 0.0
