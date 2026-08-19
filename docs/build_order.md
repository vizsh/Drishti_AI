# KINESIS AI — Build order

Build bottom-up, test each stage in isolation against real or staged footage
before wiring it into the next. A wrong assumption in an early stage silently
breaks everything built on top of it — verify before moving on.

1. **Ingestion** (`ingestion/`) — RTSP/file decode pipeline working against a
   test stream (a phone camera via an RTSP app is fine). Validate decode
   (TCP transport, correct frame rate/resolution) before any ML touches it.
2. **Person detection** (`perception/`) — YOLO11n person-class detection.
   Confirm boxes on real footage.
3. **Tracking** — add BoT-SORT. Confirm IDs persist across a short test video
   with someone walking behind an obstacle (occlusion recovery).
4. **Seat-anchoring homography** (`calibration/`) — one-time per-camera
   calibration, confirm seat-anchored identity is stable across an ID swap.
5. **Pose estimation** — add YOLO11-pose, overlay skeletons, sanity-check on
   seated-classroom footage, add One-Euro filtering.
6. **Per-seat temporal buffer + baseline calibration** — confirm it correctly
   captures a "quiet" settling window and computes sane rolling stats.
7. **Object detection** — fine-tuned YOLO11 branch for phone/paper/earpiece,
   wired in parallel with pose.
8. **Behaviour classification** (`behaviour/`) — get PYSKL/ST-GCN++ running
   on pre-recorded skeleton sequences offline first; debug accuracy before
   debugging real-time constraints.
9. **Risk engine** (`risk_engine/`) — combine baseline z-score + behaviour
   confidence + object confidence + pattern score; tune thresholds against
   staged footage with known ground truth.
10. **Backend** (`backend/`) — FastAPI + Redis Streams + WebSocket alerts,
    Postgres event log, MinIO evidence storage.
11. **Dashboard** (`dashboard/`) — React UI, build against mocked data first,
    then wire to the real pipeline.
12. **Jetson deployment** — containerize and validate on Jetson Orin Nano
    only after the full pipeline works end-to-end on the dev machine.

## Current stage

Stages 1-3 done and validated against real exam-hall footage
(`data/test_videos/`, gitignored — supplied locally, not committed):
- Ingestion + person detection (`ingestion/`, `perception/detector.py`)
- BoT-SORT tracking (`perception/tracker.py`) — confirmed real ID churn on
  real footage, motivating stage 3
- Seat-anchoring homography (`calibration/`) — confirmed seat-level identity
  is more stable than raw tracker IDs on the same footage

Next: Stage 5, YOLO11-pose + One-Euro filtering (`perception/`), then
Stage 4, the fine-tuned phone/paper/earpiece object detector, which needs a
labeled dataset (own staged footage + Roboflow/Kaggle public sets — see
docs/architecture.md §4).
