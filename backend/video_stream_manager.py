"""Part 1b (2026-08-21): user-uploaded video, served as a genuine live
RTSP feed — not read directly as a file.

Reuses the exact RTSP-simulation approach already built and validated for
ingestion testing (docs/rtsp_readiness.md): a local mediamtx server plus an
ffmpeg process pushing the uploaded file into it with `-re` (real-time
pacing) and `-stream_loop -1` (continuous). Deployment.json then points at
the resulting rtsp:// URL exactly as it would point at a real camera —
ingestion/video_source.py's is_live code path has no special case for
"this came from an upload," because there isn't one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

MEDIAMTX_DIR = Path("tools/mediamtx")
MEDIAMTX_EXE = MEDIAMTX_DIR / "mediamtx.exe"
MEDIAMTX_YML = MEDIAMTX_DIR / "mediamtx.yml"
RTSP_PORT = 8554
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ffmpeg_path_cache: Optional[str] = None
_lock = threading.Lock()
_mediamtx_proc: Optional[subprocess.Popen] = None
_streams: dict[str, subprocess.Popen] = {}  # stream_name -> ffmpeg process


def _find_ffmpeg() -> str:
    global _ffmpeg_path_cache
    if _ffmpeg_path_cache:
        return _ffmpeg_path_cache
    found = shutil.which("ffmpeg")
    if found:
        _ffmpeg_path_cache = found
        return found
    # Fall back to the winget install location used during Part 0.5's
    # ingestion validation, in case ffmpeg isn't on PATH in this shell.
    winget_glob = list(Path("C:/Users").glob("*/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    if winget_glob:
        _ffmpeg_path_cache = str(winget_glob[0])
        return _ffmpeg_path_cache
    raise RuntimeError("ffmpeg not found on PATH or in the expected winget install location")


def ensure_mediamtx_running() -> None:
    """Starts the local RTSP relay server once, if it isn't already
    running. Idempotent — safe to call before every upload."""
    global _mediamtx_proc
    with _lock:
        if _mediamtx_proc is not None and _mediamtx_proc.poll() is None:
            return  # already running
        if not MEDIAMTX_EXE.exists():
            raise RuntimeError(
                f"{MEDIAMTX_EXE} not found — mediamtx must be present locally for live-video-upload simulation "
                "(see docs/rtsp_readiness.md for how it was set up)"
            )
        _mediamtx_proc = subprocess.Popen(
            [str(MEDIAMTX_EXE), str(MEDIAMTX_YML.name)],
            cwd=str(MEDIAMTX_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def start_live_stream(video_path: Path, stream_name: str) -> str:
    """Pushes video_path into the local RTSP relay at real-time pace,
    looped indefinitely, under stream_name. Returns the rtsp:// URL to use
    as this camera's video_path in config/deployment.json. Re-encodes to
    H.264 (not -c copy) since an arbitrary user upload's original codec
    isn't guaranteed to be RTSP-streamable as-is — correctness for any
    upload matters more than CPU cost here."""
    ensure_mediamtx_running()
    stop_live_stream(stream_name)  # replace any existing stream under this name

    ffmpeg = _find_ffmpeg()
    url = f"rtsp://127.0.0.1:{RTSP_PORT}/{stream_name}"
    proc = subprocess.Popen(
        [
            ffmpeg, "-re", "-stream_loop", "-1", "-i", str(video_path),
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-an", "-f", "rtsp", "-rtsp_transport", "tcp", url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with _lock:
        _streams[stream_name] = proc
    return url


def stop_live_stream(stream_name: str) -> None:
    with _lock:
        proc = _streams.pop(stream_name, None)
    if proc is not None and proc.poll() is None:
        proc.terminate()


def stop_all_streams() -> None:
    with _lock:
        names = list(_streams.keys())
    for name in names:
        stop_live_stream(name)


_STREAM_URL_RE = re.compile(rf"rtsp://127\.0\.0\.1:{RTSP_PORT}/([A-Za-z0-9_]+)")


def stop_stream_for_url(video_path: str) -> bool:
    """Stops the ffmpeg relay behind a rtsp://127.0.0.1:8554/<name> URL, if
    that's what video_path is. Real cameras' rtsp:// URLs (a different host)
    fall straight through as a no-op. This is what disconnect_camera() was
    missing — it took the camera out of the live pipeline but never told
    the underlying ffmpeg process pushing the uploaded file to stop, so the
    -stream_loop -1 process just kept looping forever in the background."""
    match = _STREAM_URL_RE.fullmatch(video_path.strip())
    if not match:
        return False
    stop_live_stream(match.group(1))
    return True


def reap_stray_processes() -> int:
    """Startup guard (2026-08-22): if the backend process was killed/
    restarted while a live-upload stream was running, the ffmpeg/mediamtx
    child processes it spawned survive the restart as orphans — the new
    backend's _streams dict starts empty and has no PID to stop them, so
    they loop forever until someone finds and kills them by hand (the exact
    "stuck in a loop, won't stop" bug reported live). Called once at
    startup to kill any ffmpeg process still running with our -stream_loop
    signature, plus any mediamtx.exe, before this process starts tracking
    its own. Windows-only (dev/demo tooling for the upload-as-live-feed
    path, not part of the Jetson deployment target) — a no-op elsewhere."""
    if sys.platform != "win32":
        return 0
    killed = 0
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "name='ffmpeg.exe' or name='mediamtx.exe'",
             "get", "ProcessId,CommandLine"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or "ProcessId" in line:
                continue
            if "stream_loop" not in line and "mediamtx.exe" not in line:
                continue
            pid = line.split()[-1]
            if not pid.isdigit():
                continue
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
            killed += 1
    except Exception:
        pass  # best-effort — never block backend startup on this
    return killed
