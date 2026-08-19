"""Stage 0: video ingestion.

Wraps OpenCV's FFmpeg-backed VideoCapture with the constraints from
docs/architecture.md §1: TCP transport for RTSP, buffer size 1 (never queue
frames), a watchdog that reconnects on stream loss, and frame-rate downsampling
so the perception stage runs at ~10fps regardless of the source's native rate.

Works identically against an RTSP URL, a local video file, or a webcam index,
so the ingestion layer can be developed and tested without real camera hardware.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float
    frame_index: int


class VideoSource:
    """Pulls frames from an RTSP stream, video file, or webcam.

    For RTSP sources, forces TCP transport (via the FFmpeg rtsp_transport
    option) so a dropped frame during a brief occlusion or object flash never
    happens silently over UDP. Reconnects automatically if the stream drops.
    """

    def __init__(
        self,
        source: str | int,
        target_fps: float = 10.0,
        reconnect_delay_s: float = 2.0,
        max_reconnect_attempts: Optional[int] = None,
    ):
        self.source = source
        self.target_fps = target_fps
        self.reconnect_delay_s = reconnect_delay_s
        self.max_reconnect_attempts = max_reconnect_attempts
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_index = 0
        self._last_emit_time = 0.0

    def _is_rtsp(self) -> bool:
        return isinstance(self.source, str) and self.source.lower().startswith("rtsp://")

    def _open(self) -> cv2.VideoCapture:
        if self._is_rtsp():
            # TCP transport: docs/architecture.md §1 — UDP drops packets under
            # jitter, unacceptable when a dropped frame could be the exact
            # moment of a phone flash.
            import os

            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            cap = cv2.VideoCapture(self.source)

        # Buffer size 1: always read the newest frame, never a backlog.
        # "Live" silently becoming a delayed replay is the failure mode this
        # prevents (docs/architecture.md §1).
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            raise ConnectionError(f"Could not open video source: {self.source}")
        return cap

    def _reconnect(self) -> None:
        if self._cap is not None:
            self._cap.release()
        attempts = 0
        while True:
            try:
                self._cap = self._open()
                logger.info("Reconnected to source %s", self.source)
                return
            except ConnectionError:
                attempts += 1
                if self.max_reconnect_attempts is not None and attempts >= self.max_reconnect_attempts:
                    raise
                logger.warning(
                    "Failed to (re)connect to %s (attempt %d), retrying in %.1fs",
                    self.source,
                    attempts,
                    self.reconnect_delay_s,
                )
                time.sleep(self.reconnect_delay_s)

    def frames(self) -> Iterator[Frame]:
        """Yields frames downsampled to target_fps. Blocks the caller's thread.

        Live sources (RTSP/webcam) are throttled by wall-clock time, always
        reading the newest frame. A file source has no "live" concept, so it's
        downsampled by frame stride instead — processing every Nth frame based
        on the file's native fps, read as fast as decode allows.
        """
        self._reconnect()
        assert self._cap is not None
        is_live = self._is_rtsp() or isinstance(self.source, int)

        stride = 1
        if not is_live and self.target_fps > 0:
            native_fps = self._cap.get(cv2.CAP_PROP_FPS) or self.target_fps
            stride = max(1, round(native_fps / self.target_fps))

        min_interval = 1.0 / self.target_fps if (is_live and self.target_fps > 0) else 0.0
        raw_index = 0

        while True:
            assert self._cap is not None
            ok, image = self._cap.read()

            if not ok:
                if is_live:
                    logger.warning("Frame read failed for %s, reconnecting", self.source)
                    self._reconnect()
                    continue
                return  # end of file

            raw_index += 1
            now = time.monotonic()

            if is_live:
                if now - self._last_emit_time < min_interval:
                    continue  # drop frame to hit target sampling rate
            else:
                if raw_index % stride != 0:
                    continue

            self._last_emit_time = now
            self._frame_index += 1
            yield Frame(image=image, timestamp=now, frame_index=self._frame_index)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
