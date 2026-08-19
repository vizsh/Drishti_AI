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

VIDEO_PATH = "data/test_videos/04.CCTV Candidate Talking.mkv"

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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "dashboard" / "index.html")


app.mount("/dashboard", StaticFiles(directory=Path(__file__).parent.parent / "dashboard"), name="dashboard")
