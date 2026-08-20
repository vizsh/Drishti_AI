"""FastAPI backend: real-time WebSocket telemetry from the live pipeline
worker, plus the feedback-loop endpoint (docs/architecture.md §10).

Run: uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import db
from backend.pipeline_worker import PipelineWorker
from calibration.coverage import CameraCoverageInput, validate_coverage

VIDEO_PATH = "data/test_videos/04.CCTV Candidate Talking.mkv"
DEMO_FRAME_SIZE = (640, 480)  # data/test_videos/04's actual resolution

# The institution's full seating chart, in a real deployment — deliberately
# wider than the 4 seats actually calibrated in this demo, so the coverage
# check has real blind spots to report rather than always passing.
EXPECTED_SEAT_IDS = ["seat_1", "seat_2", "seat_3", "seat_4", "seat_5", "seat_6"]

app = FastAPI(title="KINESIS AI")

event_queue: "queue.Queue" = queue.Queue()
worker: PipelineWorker | None = None
connections: list[WebSocket] = []
session_id: int | None = None


@app.on_event("startup")
async def startup() -> None:
    global worker, session_id
    db.init_db()
    session_id = db.create_session(VIDEO_PATH)
    worker = PipelineWorker(VIDEO_PATH, event_queue, device="cuda", settling_seconds=20.0)
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
    when a student in a blind spot goes unmonitored. EXPECTED_SEAT_IDS
    stands in for a real institution's seating chart in this demo."""
    if worker is None:
        return {"results": []}
    width, height = DEMO_FRAME_SIZE
    camera = CameraCoverageInput(worker.seat_cal.camera_id, worker.seat_cal, width, height)
    results = validate_coverage(EXPECTED_SEAT_IDS, [camera])
    return {
        "results": [
            {"seat_id": r.seat_id, "covered": r.covered, "covering_cameras": r.covering_cameras, "reason": r.reason}
            for r in results
        ],
        "total": len(results),
        "covered_count": sum(1 for r in results if r.covered),
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "dashboard" / "index.html")


app.mount("/dashboard", StaticFiles(directory=Path(__file__).parent.parent / "dashboard"), name="dashboard")

_evidence_dir = Path(__file__).parent.parent / "data" / "evidence"
_evidence_dir.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=_evidence_dir), name="evidence")
