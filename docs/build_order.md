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

Stages 1-3, 5, and 6 done and validated against real exam-hall footage
(`data/test_videos/`, gitignored — supplied locally, not committed):
- Ingestion + person detection (`ingestion/`, `perception/detector.py`)
- BoT-SORT tracking (`perception/tracker.py`)
- Seat-anchoring homography (`calibration/homography.py`)
- YOLO11-pose + One-Euro filtering (`perception/pose.py`, `one_euro_filter.py`)
- Per-seat temporal buffer + baseline calibration (`calibration/baseline.py`)

Stage 4 (object detector) is in progress, not done:
- v1 phone detector trained (`data/weights/phone_detector_v1.pt`, gitignored)
  but found overfitting on real footage (false-positived on a chair) —
  not trustworthy yet.
- 405 candidate frames extracted from real footage and uploaded to Roboflow
  (`idibag/kinesis-ai-contraband`) for labeling — needs human labeling
  before a v2 retrain.

Next: Stage 7, the risk engine (fuse baseline z-scores + behaviour +
object-detection confidence + temporal pattern scoring into one risk value),
which can be built and tested now using Stage 6's z-scores even before the
object detector is finalized — object confidence just plugs in as one more
input once ready.
