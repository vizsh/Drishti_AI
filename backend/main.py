"""FastAPI backend: real-time WebSocket telemetry from the live pipeline
worker, plus the feedback-loop endpoint (docs/architecture.md §10).

Run: uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import queue
import time
from pathlib import Path
from typing import Annotated, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import db, video_stream_manager
from backend.deployment_config import DeploymentConfig, load_deployment_config, save_hall_cameras, set_camera_disconnected
from backend.pipeline_worker import PipelineWorker
from backend.report import generate_session_report_pdf
from calibration.blind_spot_tracker import LiveBlindSpotTracker
from calibration.coverage import CameraCoverageInput, validate_coverage
from calibration.room_scan import RoomScanSession

app = FastAPI(title="KINESIS AI")

DEMO_ACCOUNTS = {
    "controller@kinesis.ai": {"password": "demo1234", "name": "M. Chen", "role": "controller", "hall": None},
    "invigilator.a@kinesis.ai": {"password": "demo1234", "name": "R. Fernandes", "role": "invigilator", "hall": "Hall A"},
    "invigilator.b@kinesis.ai": {"password": "demo1234", "name": "S. Okafor", "role": "invigilator", "hall": "Hall B"},
}

async def get_current_user(kinesis_session_user: Annotated[str | None, Cookie()] = None) -> dict:
    if not kinesis_session_user or kinesis_session_user not in DEMO_ACCOUNTS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return DEMO_ACCOUNTS[kinesis_session_user]

@app.post("/api/login")
async def api_login(body: dict, response: Response) -> dict:
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    account = DEMO_ACCOUNTS.get(email)
    if not account or account["password"] != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )
    # Set secure HttpOnly session cookie
    response.set_cookie(
        key="kinesis_session_user",
        value=email,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=False
    )
    return {
        "status": "ok",
        "user": {
            "email": email,
            "name": account["name"],
            "role": account["role"],
            "hall": account["hall"],
            "initials": "".join([part[0] for part in account["name"].split() if part])
        }
    }

@app.post("/api/logout")
async def api_logout(response: Response) -> dict:
    response.delete_cookie(key="kinesis_session_user")
    return {"status": "ok"}

event_queue: "queue.Queue" = queue.Queue()
workers: list[PipelineWorker] = []
seat_to_worker: dict[str, PipelineWorker] = {}
# Dashboard grid (2026-08-22): a worker's OWN camera_id -> worker mapping,
# distinct from seat_to_worker, so /api/cameras/{id}/stream can find the
# right worker even before that camera has resolved any seats yet.
camera_to_worker: dict[str, PipelineWorker] = {}
connections: list[WebSocket] = []
session_id: int | None = None
deployment: DeploymentConfig | None = None
_workers_lock = asyncio.Lock()
# Part G Tier 1 (2026-08-21): current session's exam-type weight profile —
# applied to every worker's RiskEngine, and re-applied to any worker
# (re)created afterward (Part F's setup-triggered restart included), so a
# mid-session camera reconfiguration doesn't silently reset it to "mixed".
current_exam_type: str = "mixed"

# Part 1a (2026-08-21): the currently-active live blind-spot-analysis
# window, if any. Set by /api/setup/blind-spot-analysis while it runs, None
# otherwise — record_seat_observation() below is wired into every worker at
# construction time (not re-wired per-request) so it's always safe to call,
# it just no-ops when no analysis window is open.
_blind_spot_tracker: LiveBlindSpotTracker | None = None

# Lab Setup room-scan (2026-08-22): the currently-active per-camera scan
# window, if any. Distinct from _blind_spot_tracker above -- this answers
# "what does THIS one camera see, and where, right now" with real
# bounding boxes, for the setup-flow sensing animation, not a cross-
# camera coverage question.
_room_scan: RoomScanSession | None = None


def _worker_for_seat(seat_id: str) -> PipelineWorker | None:
    return seat_to_worker.get(seat_id)


def _worker_for_camera(camera_id: str) -> PipelineWorker | None:
    return camera_to_worker.get(camera_id)


def record_seat_observation(camera_id: str, seat_id: str) -> None:
    tracker = _blind_spot_tracker
    if tracker is not None:
        tracker.record(camera_id, seat_id)


def record_seat_detection(camera_id: str, seat_id: str, bbox: tuple, confidence: float, timestamp: float) -> None:
    scan = _room_scan
    if scan is not None:
        scan.record(camera_id, seat_id, bbox, confidence, timestamp)


def _start_workers() -> None:
    """One independent PipelineWorker per group of cameras that actually
    share seats (backend/deployment_config.py's worker_groups()) — a
    camera with zero seat overlap with anything else is structurally
    invisible to a single global worker's scoring loop (the Hall B bug:
    seat_7-10 never scored because they shared no seats with the Hall A
    primary). All workers share one event_queue/broadcast_loop. Only the
    group containing the deployment's original primary camera streams
    live JPEG frames — PS performance note: never decode more than one
    tile's frames for live-feed display at a time.

    Factored out of startup() (Part F, 2026-08-21) so the lab-setup flow
    can call this again after writing a new camera config, without
    restarting the whole app — same logic either way, not a second path."""
    global workers, seat_to_worker, camera_to_worker
    assert deployment is not None
    workers = []
    seat_to_worker = {}
    camera_to_worker = {}
    groups = deployment.worker_groups()
    for i, (primary, secondaries) in enumerate(groups):
        w = PipelineWorker(
            primary,
            secondaries,
            event_queue,
            settling_seconds=deployment.settling_seconds,
            object_detect_confidence=deployment.object_detect_confidence,
            device="cuda",
            stream_frames=(i == 0),
            on_seat_observed=record_seat_observation,
            on_seat_detection=record_seat_detection,
        )
        w.risk_engine.apply_profile(current_exam_type)
        workers.append(w)
        camera_to_worker[w.camera_id] = w
        for seat_id in w.seat_cal.seats:
            seat_to_worker[seat_id] = w
        w.start()


def _stop_workers() -> None:
    for w in workers:
        w.stop()


@app.on_event("startup")
async def startup() -> None:
    global session_id, deployment
    deployment = load_deployment_config()
    db.init_db()
    session_id = db.create_session(deployment.primary_camera.video_path)
    _start_workers()
    asyncio.create_task(broadcast_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    _stop_workers()


@app.post("/api/setup/cameras")
async def setup_hall_cameras(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Part F: multi-camera lab setup flow — saves this hall's camera list
    (RTSP/video sources, homography points, seat assignments) into
    config/deployment.json (backend/deployment_config.py's
    save_hall_cameras(), replacing only this hall's previous cameras), then
    reloads the config and restarts every worker against it. Two or more
    cameras assigned overlapping seats automatically become a fusion
    primary/secondary pair via the SAME worker_groups() grouping every
    other camera goes through — no separate fusion-wiring step, this *is*
    the wiring. Locked so a second setup call can't race a restart already
    in progress."""
    global deployment
    hall = body.get("hall", "Hall A")
    cameras = body.get("cameras", [])
    async with _workers_lock:
        await asyncio.to_thread(save_hall_cameras, hall, cameras)
        _stop_workers()
        deployment = load_deployment_config()
        _start_workers()
    return {"status": "ok", "hall": hall, "camera_count": len(cameras)}


async def _set_camera_connection(camera_id: str, disconnected: bool) -> dict:
    global deployment
    async with _workers_lock:
        found = await asyncio.to_thread(set_camera_disconnected, camera_id, disconnected)
        if not found:
            raise HTTPException(status_code=404, detail=f"No camera '{camera_id}' in config/deployment.json")
        _stop_workers()
        deployment = load_deployment_config()
        _start_workers()
    return {"status": "ok", "camera_id": camera_id, "disconnected": disconnected}


@app.post("/api/setup/cameras/{camera_id}/disconnect")
async def disconnect_camera(camera_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Accuracy audit (2026-08-22): takes one camera out of the live
    deployment without touching its saved calibration/seat config — its
    worker group stops, it stops streaming/scoring, and (per
    DeploymentConfig.worker_groups()) any seat ONLY it covered goes dark
    rather than silently keeping stale state. Reversible via .../reconnect."""
    return await _set_camera_connection(camera_id, True)


@app.post("/api/setup/cameras/{camera_id}/reconnect")
async def reconnect_camera(camera_id: str, user: dict = Depends(get_current_user)) -> dict:
    return await _set_camera_connection(camera_id, False)


@app.get("/api/setup/config")
async def get_setup_config(user: dict = Depends(get_current_user)) -> dict:
    """Part F: current raw deployment.json content, for the setup UI to
    show what's already configured (existing halls/cameras) before adding
    or editing more."""
    import json as _json

    from backend.deployment_config import DEFAULT_CONFIG_PATH

    return _json.loads(DEFAULT_CONFIG_PATH.read_text())


@app.post("/api/setup/blind-spot-analysis")
async def run_blind_spot_analysis(body: dict | None = None, user: dict = Depends(get_current_user)) -> dict:
    """Part 1a: LIVE blind-spot analysis — distinct from the static
    geometric /api/coverage check above. Opens a short window during which
    every running worker's real nearest_seat() resolutions (wired via
    on_seat_observed, see backend/pipeline_worker.py) get recorded against
    the actual configured cameras, then reports per-seat whether real
    detections landed from both cameras, exactly one, or neither — this is
    what genuine occlusion (a monitor, another student, a doorframe) looks
    like, which a purely geometric homography check cannot see. Requires
    >=2 configured cameras and at least one running worker."""
    global _blind_spot_tracker
    if deployment is None or len(deployment.cameras) < 2:
        raise HTTPException(
            status_code=400,
            detail="Live blind-spot analysis needs at least 2 configured cameras for this hall.",
        )
    if not workers:
        raise HTTPException(status_code=400, detail="No pipeline workers running yet — save the camera setup first.")
    duration = float((body or {}).get("duration_seconds", 8.0))
    duration = max(3.0, min(duration, 60.0))
    tracker = LiveBlindSpotTracker(duration_seconds=duration)
    _blind_spot_tracker = tracker
    try:
        await asyncio.sleep(duration)
    finally:
        _blind_spot_tracker = None
    camera_ids = [cam.camera_id for cam in deployment.cameras]
    return tracker.result(deployment.expected_seats, camera_ids)


@app.post("/api/setup/cameras/{camera_id}/scan")
async def run_room_scan(camera_id: str, body: dict | None = None, user: dict = Depends(get_current_user)) -> dict:
    """Lab Setup room-scan (2026-08-22): the real data behind the
    "sensing" animation. Opens a short window during which THIS camera's
    own worker records every real detection's bounding box + confidence
    (wired via on_seat_detection, see backend/pipeline_worker.py), then
    reports each of this camera's configured seats as visible/partial/
    occluded with a real bbox to draw and a real confidence number — never
    a fabricated one. A seat that gets zero real detections this window
    still gets a bbox (via SeatCalibration.project_inverse(), the same
    inverse-homography math /api/coverage already uses), so even "we
    never saw this seat" has a real, calibration-derived place to draw at."""
    global _room_scan
    w = _worker_for_camera(camera_id)
    if w is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{camera_id}' has no independent pipeline worker to scan (fusion-only secondary cameras have no frame loop of their own)",
        )
    duration = float((body or {}).get("duration_seconds", 5.0))
    duration = max(2.0, min(duration, 20.0))

    fallback_bboxes: dict[str, tuple] = {}
    for seat_id, plane_point in w.seat_cal.seats.items():
        cx, cy = w.seat_cal.project_inverse(plane_point)
        half = 45.0  # a reasonable placeholder box size at typical CCTV distance
        fallback_bboxes[seat_id] = (cx - half, cy - half, cx + half, cy + half)

    scan = RoomScanSession(camera_id, duration_seconds=duration)
    _room_scan = scan
    try:
        await asyncio.sleep(duration)
    finally:
        _room_scan = None
    result = scan.result(fallback_bboxes)
    result["image_width"] = w.image_width
    result["image_height"] = w.image_height
    return result


@app.post("/api/setup/upload-video")
async def upload_setup_video(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    """Part 1b: a user-uploaded video treated as a genuine LIVE feed, not a
    batch replay. Saves the upload, then spins up a local simulated RTSP
    stream (mediamtx + ffmpeg -re, see backend/video_stream_manager.py)
    serving it back out with real-time pacing, looped. Returns the
    resulting rtsp:// URL — the setup UI plugs THAT into the camera's
    video_path field, so ingestion/video_source.py's is_live flag (True
    for any rtsp:// URL) takes the exact same real-time-throttled code
    path a genuine camera would, with no special-casing for uploads."""
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    stream_name = f"upload_{int(time.time() * 1000)}"
    dest = video_stream_manager.UPLOAD_DIR / f"{stream_name}{suffix}"
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    rtsp_url = await asyncio.to_thread(video_stream_manager.start_live_stream, dest, stream_name)
    return {"status": "ok", "stream_name": stream_name, "rtsp_url": rtsp_url, "filename": file.filename}


@app.post("/api/session/exam-type")
async def set_exam_type(body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Part G Tier 1: applies an exam-type weight profile (mcq/written/
    mixed) to every current worker's RiskEngine in place — no restart, no
    loss of in-progress calibration/deviation-tracking state, just a
    change in how already-computed signals get weighted. Also remembered
    so a later Part-F camera reconfiguration re-applies it instead of
    silently resetting to "mixed"."""
    global current_exam_type
    exam_type = body.get("exam_type", "mixed")
    if exam_type not in ("mcq", "written", "mixed"):
        exam_type = "mixed"
    current_exam_type = exam_type
    for w in workers:
        w.risk_engine.apply_profile(exam_type)
    return {"status": "ok", "exam_type": exam_type}


@app.get("/api/session/exam-type")
async def get_exam_type(user: dict = Depends(get_current_user)) -> dict:
    return {"exam_type": current_exam_type}


async def broadcast_loop() -> None:
    while True:
        drained = []
        try:
            while True:
                drained.append(event_queue.get_nowait())
        except queue.Empty:
            pass

        if drained:
            dead = []
            for ws in connections:
                try:
                    for event in drained:
                        await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in connections:
                    connections.remove(ws)

            if session_id is not None:
                await asyncio.to_thread(db.log_events, session_id, drained)

        await asyncio.sleep(0.05)


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    session_user = websocket.cookies.get("kinesis_session_user")
    if not session_user or session_user not in DEMO_ACCOUNTS:
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)


@app.get("/api/seats")
async def get_seats(user: dict = Depends(get_current_user)) -> dict:
    return {"seats": sorted(seat_to_worker.keys())}


@app.get("/api/cameras")
async def get_cameras(user: dict = Depends(get_current_user)) -> dict:
    """Configured cameras, for the /live multi-camera grid — driven by
    config/deployment.json, not a hardcoded frontend count. Only the
    primary camera streams a live JPEG feed (WebSocket "frame" events);
    secondary cameras (potentially simulated, see config/deployment.json's
    cam_b_SIMULATED comment) feed occlusion fusion only and have no visual
    stream of their own — the frontend must not pretend otherwise."""
    if deployment is None:
        return {"cameras": []}
    result = []
    for cam in deployment.cameras:
        w = camera_to_worker.get(cam.camera_id)
        # Dashboard grid (2026-08-22): stream_mode now reflects the actual
        # live, settable state of that camera's own worker — "off" for a
        # true fusion-only secondary (e.g. cam_b_SIMULATED) that never gets
        # its own PipelineWorker at all, not a static i==0 guess.
        stream_mode = w.stream_mode if w is not None else "off"
        result.append(
            {
                "camera_id": cam.camera_id,
                "hall": cam.hall,
                "video_path": cam.video_path,
                "video_paths": cam.playlist,
                "is_simulated": cam.is_simulated,
                "disconnected": cam.disconnected,
                "is_primary": stream_mode == "focused",
                "seats": sorted(cam.calibration.seats.keys()),
                "streams_live_feed": stream_mode != "off",
                "stream_mode": stream_mode,
                "has_own_worker": w is not None,
            }
        )
    return {"cameras": result}


@app.post("/api/cameras/{camera_id}/stream")
async def set_camera_stream_mode(camera_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Dashboard grid (2026-08-22): lets the frontend request "background"
    (low-rate grid thumbnail) or "focused" (full-rate single view) for any
    camera that has its own PipelineWorker — the fix for "only one camera
    ever streams." Returns 404 for a camera with no worker of its own
    (a true fusion-only secondary, e.g. cam_b_SIMULATED) since there is no
    frame-decode loop to turn on for those, and that's a real fact about
    the deployment, not a bug to silently swallow."""
    mode = body.get("mode", "background")
    if mode not in ("off", "background", "focused"):
        raise HTTPException(status_code=400, detail=f"mode must be one of off/background/focused, got {mode!r}")
    w = _worker_for_camera(camera_id)
    if w is None:
        raise HTTPException(
            status_code=404,
            detail=f"'{camera_id}' has no independent pipeline worker (fusion-only secondary cameras have no visual feed to stream)",
        )
    w.set_stream_mode(mode)
    return {"status": "ok", "camera_id": camera_id, "stream_mode": mode}


@app.post("/api/alerts/{seat_id}/dismiss")
async def dismiss_alert(seat_id: str, body: dict | None = None, user: dict = Depends(get_current_user)) -> dict:
    """Phase 4: extends the original dismiss-as-false-positive endpoint with
    a resolution taxonomy (false_alarm/confirmed/no_action) instead of a
    second, disconnected mechanism — same worker method, same feedback-loop
    event path. body: {"resolution": "false_alarm"|"confirmed"|"no_action",
    "invigilator": str | null}. Missing body/resolution defaults to
    false_alarm, preserving the original one-click dismiss behaviour."""
    resolution = (body or {}).get("resolution", "false_alarm")
    invigilator = (body or {}).get("invigilator")
    w = _worker_for_seat(seat_id)
    if w is not None:
        w.resolve_alert(seat_id, resolution, invigilator)
    return {"status": "ok", "seat_id": seat_id, "resolution": resolution}


@app.post("/api/alerts/{seat_id}/acknowledge")
async def acknowledge_alert(seat_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Part 6: lightweight "seen, noted" action distinct from dispatch/
    resolve - for a minor item that doesn't need the full workflow. Logged
    for the audit trail; doesn't touch calibration."""
    invigilator = body.get("invigilator", "unknown")
    w = _worker_for_seat(seat_id)
    if w is not None:
        w.acknowledge_alert(seat_id, invigilator)
    return {"status": "ok", "seat_id": seat_id, "invigilator": invigilator}


@app.post("/api/alerts/{seat_id}/dispatch")
async def dispatch_invigilator(seat_id: str, body: dict, user: dict = Depends(get_current_user)) -> dict:
    """Phase 4: "Dispatch Invigilator" action in the investigation view —
    auto-filled invigilator name from the logged-in user, timestamp logged
    server-side (created_at on the persisted event)."""
    invigilator = body.get("invigilator", "unknown")
    w = _worker_for_seat(seat_id)
    if w is not None:
        w.dispatch_invigilator(seat_id, invigilator)
    return {"status": "ok", "seat_id": seat_id, "invigilator": invigilator}


@app.get("/api/events")
async def get_events(
    seat_id: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    limit: int = 200,
    all_sessions: bool = False,
    user: dict = Depends(get_current_user),
) -> dict:
    """PS #1 objective: "event logs for invigilator review" — persisted,
    filterable, survives a page refresh or server restart (unlike the
    in-memory alert feed alone)."""
    sid = None if all_sessions else session_id
    events = await asyncio.to_thread(db.query_events, sid, seat_id, event_type, search, limit)
    return {"events": events, "session_id": session_id}


@app.get("/api/analytics")
async def get_analytics(all_sessions: bool = False, seat_ids: str | None = None, user: dict = Depends(get_current_user)) -> dict:
    """PS #1 objective: "behavioral analytics ... for invigilator review".
    seat_ids: optional comma-separated hall-scoping filter so an
    Invigilator's stat strip reflects only their assigned hall."""
    sid = None if all_sessions else session_id
    scoped = seat_ids.split(",") if seat_ids else None
    return await asyncio.to_thread(db.analytics_summary, sid, scoped)


@app.get("/api/report")
async def get_session_report(seat_ids: str | None = None, user: dict = Depends(get_current_user)) -> Response:
    """Phase 6: "Export Session Report" - pulls real session data (analytics
    summary, full alert log with best-effort resolution correlation,
    dispatch/resolution log) at export time, not a cached/static file.
    seat_ids: optional hall-scoping filter, same pattern as /api/analytics,
    so an Invigilator's export reflects only their assigned hall."""
    scoped = seat_ids.split(",") if seat_ids else None
    pdf_bytes = await asyncio.to_thread(generate_session_report_pdf, session_id, scoped)
    filename = f"kinesis_session_{session_id}_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/seats/{seat_id}/baseline")
async def get_seat_baseline(seat_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Part 2.6: personal-baseline numbers for the Digital Twin view — this
    seat's own settling-window mean/std, not a flat threshold, since that's
    the system's core differentiator the view exists to demonstrate."""
    w = _worker_for_seat(seat_id)
    baseline = w.seat_baseline(seat_id) if w is not None else None
    return {"seat_id": seat_id, "calibrated": baseline is not None, "baseline": baseline}


@app.get("/api/calibration-quality")
async def get_calibration_quality(user: dict = Depends(get_current_user)) -> dict:
    """Part 2.5: live per-camera seat-anchor hit-rate, alongside the static
    /api/coverage geometric check. "gathering" until enough samples exist to
    judge, "needs_attention" below the low-confidence threshold, else
    "good". Only covers primary cameras (one per worker_groups() group) —
    secondary/fusion-only cameras don't run their own scoring loop."""
    return {"cameras": [w.calibration_quality() for w in workers]}


@app.get("/api/coverage")
async def get_coverage(user: dict = Depends(get_current_user)) -> dict:
    """Pre-exam camera blind-spot check (docs/architecture.md §13,
    differentiator #10) — run before an exam starts, not discovered mid-exam
    when a student in a blind spot goes unmonitored. Checks every camera in
    config/deployment.json against expected_seats (the institution's
    seating chart in a real deployment)."""
    if deployment is None:
        return {"results": []}
    cameras = [
        CameraCoverageInput(cam.camera_id, cam.calibration, cam.image_width, cam.image_height)
        for cam in deployment.cameras
    ]
    results = validate_coverage(deployment.expected_seats, cameras)
    return {
        "results": [
            {"seat_id": r.seat_id, "covered": r.covered, "covering_cameras": r.covering_cameras, "reason": r.reason}
            for r in results
        ],
        "total": len(results),
        "covered_count": sum(1 for r in results if r.covered),
    }


@app.get("/api/heatmap")
async def get_heatmap(user: dict = Depends(get_current_user)) -> Response:
    """Session-wide motion heatmap (perception/motion_heatmap.py) — a
    PS #2-style output ("motion heatmaps") computed as a free byproduct of
    frames PS #1's live pipeline already decodes, not a separate offline
    pass. Useful for PS #1 directly: an invigilator can see at a glance
    where activity concentrated in the room over the whole session."""
    if not workers:
        return Response(status_code=503, content=b"pipeline not ready yet")
    # Primary hall's worker only — matches the single live-feed camera and
    # keeps this a lightweight glance, not a merged-multi-hall heatmap.
    jpeg_bytes = await asyncio.to_thread(workers[0].render_heatmap_jpeg)
    if jpeg_bytes is None:
        return Response(status_code=503, content=b"no frames processed yet")
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@app.get("/api/evidence-access-log")
async def get_evidence_access_log(clip_id: str | None = None, limit: int = 200, user: dict = Depends(get_current_user)) -> dict:
    """PS risk table row "Privacy Concerns" — who viewed which evidence
    clip, when. Read side of the audit trail written by
    get_evidence_manifest below."""
    return {"log": await asyncio.to_thread(db.query_evidence_access, clip_id, limit)}


_root_dir = Path(__file__).parent.parent
_frontend_dist = _root_dir / "frontend" / "dist"
_classic_dashboard = _root_dir / "dashboard"


@app.get("/")
async def index() -> FileResponse:
    # React frontend (frontend/) is the primary UI; the original vanilla
    # dashboard stays reachable at /dashboard-classic as a fallback rather
    # than being deleted — same working backend, two clients.
    if (_frontend_dist / "index.html").exists():
        return FileResponse(_frontend_dist / "index.html")
    return FileResponse(_classic_dashboard / "index.html")


_evidence_dir = _root_dir / "data" / "evidence"
_evidence_dir.mkdir(parents=True, exist_ok=True)


@app.get("/evidence/{clip_id}/manifest.json")
async def get_evidence_manifest(clip_id: str, request: Request, user: dict = Depends(get_current_user)) -> FileResponse:
    """Explicit route ahead of the /evidence static mount below, so every
    clip *open* (fetching its manifest is the dashboard's entry point for
    viewing one) is logged with the viewer's address — audit logging the
    PS's own "Privacy Concerns" risk row asks for, not left as a silent
    static-file fetch. Individual frame_NNN.jpg images still fall through
    to the plain static mount, which is fine — the manifest fetch is a
    reliable, low-noise proxy for "this clip was opened."""
    client_ip = request.client.host if request.client else "unknown"
    await asyncio.to_thread(db.log_evidence_access, clip_id, client_ip)
    manifest_path = _evidence_dir / clip_id / "manifest.json"
    return FileResponse(manifest_path, media_type="application/json")


@app.get("/evidence/{clip_id}/{filename}")
async def get_evidence_file(clip_id: str, filename: str, user: dict = Depends(get_current_user)) -> FileResponse:
    """Secure serving of individual frames/images inside the evidence folders.
    Enforces authentication and prevents directory traversal attacks."""
    safe_clip_id = Path(clip_id).name
    safe_filename = Path(filename).name
    file_path = _evidence_dir / safe_clip_id / safe_filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "application/octet-stream"
    return FileResponse(file_path, media_type=media_type)


app.mount("/dashboard-classic", StaticFiles(directory=_classic_dashboard, html=True), name="dashboard-classic")
if (_frontend_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="frontend-assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str) -> FileResponse:
    """React Router uses real browser URLs (BrowserRouter, not hash-based),
    so a direct navigation or refresh on e.g. /overview or /seat/seat_1 hits
    the server, not just client-side JS — without this catch-all (registered
    last, after every real route/mount above so it never shadows them) that
    would 404 instead of loading the app and letting the router take over.
    Deliberately does NOT catch /api, /ws, /evidence, /assets, /dashboard-
    classic — those are handled by the explicit routes/mounts above."""
    return await index()
