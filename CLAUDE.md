# KINESIS AI — real-time exam behaviour monitoring (PS #1, Drishti AI Hackathon)

## Why
Real-time AI system that monitors seated exam students via CCTV, flags potential
misconduct with explainable alerts (never direct accusations), and avoids
face-recognition-based identity to preserve privacy. The PS's own named risk #1
is false positives from normal student behaviour (thinking, stretching, looking
around) — every design decision here exists to reduce that specific failure
mode without losing recall on real misconduct. See [docs/architecture.md](docs/architecture.md)
for the full pipeline and rationale, and [docs/build_order.md](docs/build_order.md)
for the stage-by-stage assembly order.

## What
Pipeline: RTSP/ONVIF ingest (hardware decode, TCP transport, ~10fps sampling) →
YOLO11n person detection → BoT-SORT tracking → homography-based seat anchoring
(identity = seat, not track ID or face) → YOLO11-pose (One-Euro filtered) +
fine-tuned YOLO11 object detector (phone/paper/earpiece) → per-seat temporal
buffer with baseline calibration (z-score deviation from that student's own
settling-window stats, not a flat threshold) → ST-GCN++ (PYSKL) + rule-based
behaviour scoring fused in parallel → risk fusion engine → FastAPI/WebSocket →
React dashboard with template-based explanations and a feedback loop (dismissed
alerts widen that student's threshold live).

## Tech stack
- Ingestion: GStreamer/OpenCV (FFmpeg backend), ONVIF discovery
- Perception: Python, Ultralytics YOLO11 (detect + pose), BoT-SORT, OpenCV, PYSKL (ST-GCN++)
- Backend: FastAPI, Redis Streams, Postgres, MinIO (S3-compatible, on-prem)
- Frontend: React, WebSocket client, recharts
- Deployment target: NVIDIA Jetson Orin Nano (edge, production); dev/demo on RTX GPU

## Build order — build and test each stage in isolation before wiring to the next
See [docs/build_order.md](docs/build_order.md) for full detail. Order:
ingestion → person detection → tracking → seat-anchoring homography → pose →
object detection → temporal buffer/calibration → behaviour classification →
risk engine → backend/dashboard → Jetson deployment.

## Non-negotiable design constraints
- No face recognition, ever. Identity is seat-anchored via homography, never a face embedding.
- Raw video never leaves the edge process boundary. Only metadata (keypoints, risk
  scores, face-blurred evidence clips for confirmed alerts) crosses to backend/storage.
- Every alert must carry a deterministic, template-based explanation built from
  measured features (angle, duration, deviation-from-baseline) — never a bare
  confidence score, never a generative explanation.
- Score against each student's own calibrated baseline (z-score), not a global
  fixed threshold — this is the single highest-leverage fix for false positives.
- TCP for RTSP transport, hardware decode (NVDEC on Jetson), substream for
  inference / main stream only for confirmed-alert evidence capture.

## How to work with this repo
- Never commit /data (staged footage, model weights) — see .gitignore.
- Each pipeline stage (ingestion/, perception/, calibration/, behaviour/,
  risk_engine/, backend/, dashboard/) should run and be testable standalone
  before being wired into the next stage.
- Prefer pretrained/transfer-learned models over training from scratch — the
  project has no large labeled exam-cheating dataset; fine-tune COCO/NTU-RGB+D
  pretrained weights on small staged + public datasets instead.
- When adding a new pipeline stage, read the relevant section of
  [docs/architecture.md](docs/architecture.md) first and propose a plan before writing code.
