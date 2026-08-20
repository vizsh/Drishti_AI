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

Stage 7 (risk engine, `risk_engine/`) done — fuses baseline z-scores +
sustained-event detection + pattern scoring into one risk value with
deterministic explanations. Validated on real footage: real alerts fired
with correct text.

Stage 9 (backend + dashboard) done — `backend/` runs the real pipeline live
on a background thread, streams telemetry/alerts over WebSocket;
`dashboard/index.html` is a live single-page UI (seating grid, risk trend
chart, alert feed with a working dismiss/feedback-loop button). Verified
end-to-end in-browser against the real running server.

Stage 8 (rule-based component, `behaviour/gestures.py`) done — hand_reach_across,
a geometrically-grounded detector (wrist projects into a neighbor seat's
zone via the same homography as Stage 3) for the PS's explicitly named
"unusual hand movements" objective. Deliberately does NOT include a
flat-threshold "lean toward neighbor" detector: an early version had one,
and testing against real footage caught it firing constantly on a seat
whose camera-angle baseline alone crossed the threshold — the exact
false-positive failure mode Stage 6 exists to eliminate. Stage 7's z-score
deviation event already covers sustained lean/turn correctly. Wired into
the live dashboard (backend/pipeline_worker.py) as a distinct "GESTURE"
alert type, verified firing in-browser against the real running server.

ST-GCN++ (PYSKL) — the ML half of Stage 8 per docs/architecture.md §6 — is
NOT implemented. It needs labeled exam-specific gesture clips, which don't
exist yet; the same Roboflow labeling pass already in flight for the
object detector would need extending to short gesture clips to unblock it.
Deferred, not abandoned — the rule-based signal above is designed to keep
running alongside it once it exists, per the architecture doc's own
"hybrid" guidance.

Persistent event-log storage + analytics (`backend/db.py`) done — closes
the "behavioral analytics and event logs for invigilator review" PS
objective, which the in-memory-only alert feed didn't actually satisfy.
SQLAlchemy over SQLite by default (neither Postgres nor Docker are
available in this dev environment); DATABASE_URL swaps to a Postgres DSN
for the production target with no schema/query changes. Verified a full
page reload preserves the alert count and complete event history.

Face-blurred evidence clip capture (`backend/evidence.py`) done — closes
the privacy row of the PS's risk table ("only face-blurred evidence clips
may leave the edge boundary"). Head bboxes derived from pose keypoints
(reusing Stage 5, not a new face-detection dependency) after two dead ends:
cv2.CascadeClassifier doesn't exist in this OpenCV 5.0 build, and no H.264
encoder is available so cv2.VideoWriter mp4 output doesn't play in Chrome —
clips are a JPEG sequence + manifest instead, played back client-side.
Verified: alert fired, evidence button appeared, clip played with every
face blurred.

387/405 candidate frames uploaded to Roboflow
(idibag/kinesis-ai-contraband) for labeling — 18 failed on a transient DNS
blip, retryable via tools/upload_to_roboflow.py.

Next: retrain the Stage 4 object detector once labeling is done, then
Jetson deployment packaging. Known open gaps vs. the PS's risk table
(tracked honestly, not hidden): occlusion handling (multi-camera fusion,
single camera only today), poor-lighting robustness (CLAHE preprocessing,
not implemented), camera blind-spot coverage validator, and evidence-clip
access audit logging (who viewed which clip, when).
