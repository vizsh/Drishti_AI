"""FastAPI backend: real-time WebSocket telemetry from the live pipeline
worker, plus the feedback-loop endpoint (docs/architecture.md §10).

Run: uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import db
from backend.deployment_config import DeploymentConfig, load_deployment_config
from backend.pipeline_worker import PipelineWorker
from calibration.coverage import CameraCoverageInput, validate_coverage

app = FastAPI(title="KINESIS AI")

event_queue: "queue.Queue" = queue.Queue()
worker: PipelineWorker | None = None
connections: list[WebSocket] = []
session_id: int | None = None
deployment: DeploymentConfig | None = None


@app.on_event("startup")
async def startup() -> None:
    global worker, session_id, deployment
    deployment = load_deployment_config()
    db.init_db()
    session_id = db.create_session(deployment.primary_camera.video_path)
    worker = PipelineWorker(deployment, event_queue, device="cuda")
    worker.start()
    asyncio.create_task(broadcast_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    if worker is not None:
        worker.stop()


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
    await websocket.accept()
    connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connections:
            connections.remove(websocket)


@app.get("/api/seats")
async def get_seats() -> dict:
    if worker is None:
        return {"seats": []}
    return {"seats": sorted(worker.seat_cal.seats.keys())}


@app.post("/api/alerts/{seat_id}/dismiss")
async def dismiss_alert(seat_id: str) -> dict:
    if worker is not None:
        worker.dismiss_alert(seat_id)
    return {"status": "ok", "seat_id": seat_id}


@app.get("/api/events")
async def get_events(
    seat_id: str | None = None,
    event_type: str | None = None,
    search: str | None = None,
    limit: int = 200,
    all_sessions: bool = False,
) -> dict:
    """PS #1 objective: "event logs for invigilator review" — persisted,
    filterable, survives a page refresh or server restart (unlike the
    in-memory alert feed alone)."""
    sid = None if all_sessions else session_id
    events = await asyncio.to_thread(db.query_events, sid, seat_id, event_type, search, limit)
    return {"events": events, "session_id": session_id}


@app.get("/api/analytics")
async def get_analytics(all_sessions: bool = False) -> dict:
    """PS #1 objective: "behavioral analytics ... for invigilator review"."""
    sid = None if all_sessions else session_id
    return await asyncio.to_thread(db.analytics_summary, sid)


@app.get("/api/coverage")
async def get_coverage() -> dict:
    """Pre-exam camera blind-spot check (docs/architecture.md §13,
    differentiator #10) — run before an exam starts, not discovered mid-exam
    when a student in a blind spot goes unmonitored. Checks every camera in
    config/deployment.json against expected_seats (the institution's
    seating chart in a real deployment)."""
    if worker is None or deployment is None:
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


@app.get("/api/evidence-access-log")
async def get_evidence_access_log(clip_id: str | None = None, limit: int = 200) -> dict:
    """PS risk table row "Privacy Concerns" — who viewed which evidence
    clip, when. Read side of the audit trail written by
    get_evidence_manifest below."""
    return {"log": await asyncio.to_thread(db.query_evidence_access, clip_id, limit)}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "dashboard" / "index.html")


_evidence_dir = Path(__file__).parent.parent / "data" / "evidence"
_evidence_dir.mkdir(parents=True, exist_ok=True)


@app.get("/evidence/{clip_id}/manifest.json")
async def get_evidence_manifest(clip_id: str, request: Request) -> FileResponse:
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


app.mount("/dashboard", StaticFiles(directory=Path(__file__).parent.parent / "dashboard"), name="dashboard")
app.mount("/evidence", StaticFiles(directory=_evidence_dir), name="evidence")
