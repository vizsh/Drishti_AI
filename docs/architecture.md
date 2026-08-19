# KINESIS AI — Architecture

Problem statement: PS #1, "Behaviour Intelligence Platform for Smart Examination
Monitoring." Real-time computer vision on 30-60 seated students simultaneously,
on CCTV/hardware we don't control, producing explainable alerts an invigilator
will actually trust — not bounding boxes. Every component below exists because a
specific failure mode would otherwise break the system; failure modes are drawn
from the PS's own risk table plus operational risks it doesn't name but that hit
in practice.

## 1. Ingestion layer

**Problem it solves:** you don't get frames, you get an RTSP stream from a camera
you didn't design. Two camera families exist in the field: legacy analog CCTV
(BNC → DVR, needs an IP encoder) and modern IP cameras (native RTSP over RTP,
H.264/H.265).

Decode pipeline:
```
Camera → RTSP (RTP/H.264) → rtspsrc → depay → parse → decode → raw frame → model
```
GStreamer example (Jetson hardware decode):
```
rtspsrc location=rtsp://cam-ip/stream1 protocols=tcp latency=100 ! rtph264depay ! h264parse ! nvv4l2decoder ! nvvidconv ! appsink
```
Or `cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)` for a quick dev-time path.

| Decision | Options compared | Choice | Why |
|---|---|---|---|
| Transport | UDP vs TCP | **TCP** | UDP drops packets under jitter; a dropped frame during the 2s someone flashes a phone is unacceptable. |
| Decode | Software (avdec_h264) vs hardware (nvv4l2decoder/NVDEC) | **Hardware** | Software-decoding 4+ streams saturates CPU before the model runs; HW decode is near-free on Jetson/RTX. |
| Frame rate to models | Native 25-30fps vs downsampled | **~10fps** for detection/pose; full-rate only for saved evidence clips | Head turns/hand movements are visible at 8-10fps; 3x the rate buys 0% accuracy for 3x compute. |
| Resolution | Main stream vs substream | **Substream for inference**, main stream only for confirmed-alert zoom capture | Detection/pose don't need 1080p; cuts bandwidth/compute 4-8x with negligible accuracy loss. |
| Camera discovery | Custom per-vendor vs standard protocol | **ONVIF Profile S** | Institutions run mixed brands (Hikvision, Dahua, CP Plus); ONVIF avoids per-vendor integration code. |

Never let frames queue: always grab-then-discard-then-grab (buffer size 1) with
a watchdog that restarts the stream on disconnect — otherwise "live" silently
becomes a delayed replay by exam end.

## 2. Perception layer

**Problem it solves:** find every seated student, keep identity stable, extract
skeletons — the foundation everything downstream reads from.

| Sub-task | Options | Choice | Why |
|---|---|---|---|
| Person detection | YOLO11n vs RTMDet-tiny vs Faster-RCNN/DETR | **YOLO11n** (COCO-pretrained, person class only) | Direct TensorRT `.engine` export for Jetson matters more than 1-2 mAP points on a $200 edge box; Faster-RCNN/DETR too slow for real-time edge. No fine-tuning needed. |
| Tracking | DeepSORT vs ByteTrack vs BoT-SORT vs OC-SORT | **BoT-SORT** | Extends ByteTrack with camera-motion compensation + lightweight ReID; better fit at 15-40 objects/camera (a real exam hall camera). Motion compensation also absorbs HVAC/fan vibration on fixed mounts. ~8-15ms/frame added on Jetson at 10fps — acceptable. Ultralytics' own default tracker. |
| Pose estimation | MediaPipe (BlazePose) vs YOLO11-pose vs RTMPose vs OpenPose vs ViTPose | **YOLO11-pose primary, RTMPose CPU-only fallback** | MediaPipe is high-FPS but underperforms in dense/occluded scenes (30-60 seat hall is exactly that case). OpenPose is non-commercial licensed (disqualifying). ViTPose needs server-GPU compute. COCO-pretrained weights are fine — no custom training needed for body keypoints. |
| Keypoint stability | Raw per-frame vs filtered | **One-Euro filter** on all keypoints | Downstream angle thresholds fire on raw jitter otherwise; cheap, high-value addition almost nobody bothers with. |

## 3. Identity persistence layer (seat anchoring)

**Problem it solves:** even BoT-SORT can swap IDs across a multi-second
occlusion. Attributing seat 12's history to seat 11 after an ID swap produces
the PS's named worst case: a false accusation against the wrong student.

**Mechanism — homography-based seat anchoring, not appearance re-ID:**
1. One-time per-camera calibration: 4+ known image points ↔ real-world floor
   coordinates → `cv2.findHomography()`.
2. Every frame: project each tracked person's foot-point (bbox bottom-center)
   through the homography into room coordinates.
3. Snap to nearest seat in a pre-loaded seating chart.
4. Identity becomes `seat_34`, never `track_187` — a tracker ID swap after
   occlusion doesn't matter because the seat re-anchors identity independent
   of tracker continuity.

Near-zero additional cost once detection runs; directly answers the PS's
top-named tracking risk in a way "we use BoT-SORT" alone does not.

## 4. Object detection layer (phone / paper / earpiece)

**Problem it solves:** explicit PS objective — no pretrained model does this,
it's custom by definition.

**Dataset strategy (combine, don't rely on one source):**
- Roboflow Universe: "exam cheating" (152 images), a 313-image set with a
  pretrained baseline, a 1,798-image person-phone-calculator cheating set.
- Kaggle: classroom-exam-cheating-detection, exam-cheating-dataset.
- **Own staged footage is not optional.** Public sets are close-up, well-lit,
  single-angle; none match "phone held low, seen from an overhead CCTV at
  distance." Domain match beats volume — 200-300 own images from the actual
  camera/room/distance outweighs 2,000 mismatched public ones.

**Model:** fine-tune YOLO11n/s from COCO weights on the merged set (transfer
learning, not from-scratch). Classes: `phone`, `paper_chit`, `earpiece` (hard
at distance — be honest about this rather than overclaiming),
`hand_reaching_across`.

## 5. Temporal buffer + baseline calibration

Per-seat `collections.deque(maxlen=N)` storing `(timestamp, keypoints, box)`
for the last 5-10 seconds. No library needed.

**Baseline calibration — the single highest-leverage fix for false positives**
(PS risk #1, caused explicitly by "normal student actions... may be incorrectly
flagged"):
1. First 2-3 minutes of the exam (instructions, paper distribution) = a
   "settling window," captured automatically once a student is tracked.
2. Compute rolling mean/std (numpy) of that student's head-yaw range and
   motion magnitude during the window. Store as a personal profile keyed to
   seat ID.
3. Score subsequent behaviour as **z-score deviation from that student's own
   baseline**, never an absolute angle threshold.

## 6. Behaviour classification layer

**Problem it solves:** a single frame can't distinguish "sustained suspicious
head turn" from "glanced at the clock" — needs temporal reasoning over a
sequence.

| Option | Fit |
|---|---|
| Pure rule-based (angle + duration thresholds) | Zero training data, fully explainable, but brittle across body types, reviewers see through it fast. |
| **ST-GCN++ via PYSKL** | Maintained toolbox, ships pretrained ST-GCN++ checkpoints on NTU RGB+D (56,880 skeleton sequences, 60 classes), supports custom skeleton layouts and real-time inference. |
| Raw-video 3D CNN (SlowFast) | Needs RGB not skeletons — reintroduces the identity-bearing-video privacy problem for no behaviour-specific gain. |

**Choice: hybrid.** ST-GCN++ fine-tuned from NTU-pretrained weights on a small
labeled clip set of exam-specific behaviours (head-turn-sustained,
lean-toward-neighbor, hand-to-desk-object, normal-baseline), running in
**parallel** with rule-based thresholds; both signals combine in the risk
engine. Don't train ST-GCN from zero on a few hundred clips — it will overfit.
Rule-based is the fallback signal and fallback explanation source, and an
honest answer to "how much data did you train on." PYSKL needs a custom
skeleton layout added to `pyskl/utils/graph.py` since YOLO11-pose emits COCO
17-point, not NTU's 25-point Kinect skeleton.

## 7. Risk engine

Deterministic Python/numpy: per-seat baseline z-score + ST-GCN classification
confidence + object-detection confidence + event-pattern score (below),
combined via a weighted sum (hand-tuned initially; upgrade to scikit-learn
logistic regression if labeled "was this actually suspicious" data exists).

**Temporal pattern scoring, not single-event scoring:** keep a 5-10 minute
sliding window of discrete events per student. "3 head turns toward the same
neighbor within 2 minutes" is a different risk category than "1 six-second
glance" — a simple state machine over the event stream is enough. Real
cheating is repetitive by nature; a single glance rarely is.

## 8. Robustness layers (the physical-world risks)

- **Occlusion / blind spots:** multi-camera confidence fusion — when two
  cameras cover the same seat, fuse pose/object detections with confidence
  weighting (logical OR for object presence, weighted average for pose
  confidence) instead of trusting one camera alone. Reuses the per-camera
  homography already built for seat-anchoring.
- **Poor lighting:** apply CLAHE as a lightweight preprocessing step when mean
  frame brightness falls below a threshold — CLAHE achieves the strongest
  detection rate among lighting-enhancement methods while staying real-time
  compatible. Combine with brightness/shadow augmentation in training data,
  not preprocessing alone.
- **Head pose unreliable at CCTV distance:** fine head/eye keypoints have too
  few usable pixels at distance. Use torso/shoulder orientation (yaw from
  shoulder-to-hip vector) as the primary directional signal; only trust
  fine head-yaw when keypoint confidence exceeds a threshold, else fall back
  to torso-based estimate.
- **Network/hardware failure:** per-camera heartbeat monitoring — a dropped
  stream shows "seat coverage degraded — camera 2 offline" on the dashboard,
  not silence.

## 9. Privacy (solved architecturally, not just "pose not faces")

- Perception (detection/pose/object) runs on an edge box physically in the
  room — raw video never crosses the network.
- Only metadata (keypoints, risk scores, short evidence clips for confirmed
  high-risk events) leaves the box.
- Evidence clips are face-blurred by default before storage.
- Every clip access is audit-logged (who viewed it, when).
- Skeleton-based recognition structurally erases identity-bearing appearance
  data, which is why pose is used over raw-RGB action recognition throughout.

## 10. Dashboard / explanation layer

**Problem it solves:** PS objective — "explainable alerts... rather than
direct accusations." Detections without explanation are unusable to an
invigilator and erode trust exactly as the PS warns.

- **Deterministic, template-based explanations** built from measured
  features, never generative: *"Head yaw held 42° toward seat 33 for 6.4s —
  3.2× this student's baseline. No object detected."* Auditable, can't
  hallucinate a reason that didn't happen.
- **Feedback loop:** dismissing an alert as false positive visibly widens
  that student's baseline threshold live — the concrete, demoable answer to
  "how do you reduce false positives over time."
- **Confidence-aware UI states:** low keypoint confidence (distant seat, poor
  angle) shows "low confidence — visual check recommended," not a
  false-precision risk number.
- Seating-grid live view + per-seat risk trend graph, not just a raw alert
  list.

## 11. Backend, end to end

```
Camera → RTSP/ONVIF → edge decode (Jetson/NVDEC)
   → YOLO11n detect → BoT-SORT track → homography seat-anchor
   → YOLO11-pose (One-Euro filtered) ─┬→ per-seat temporal buffer (baseline calc)
   → fine-tuned object detector ──────┤        │
                                       ▼        ▼
                              ST-GCN++ (PYSKL) + rule-based thresholds
                                       │
                              risk engine (weighted fusion, z-score deviation)
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                                      ▼
        FastAPI + Redis Streams + WebSocket        Postgres (session/event log)
                    │                                MinIO (face-blurred clips)
                    ▼
          React dashboard (seating grid, alert feed, feedback loop)
```

| Layer | Options compared | Choice | Why |
|---|---|---|---|
| API/alerts | Flask vs FastAPI vs Django | **FastAPI** | Native async + native WebSocket for live alert push, auto OpenAPI docs, low boilerplate. |
| Message bus | Kafka vs Redis Streams vs in-process queue | **Redis Streams** | Kafka's operational overhead isn't justified at single-hall/hackathon scale; Redis gives decoupling + doubles as cache. |
| Time-series storage | InfluxDB vs TimescaleDB vs plain Postgres table | **Plain Postgres** (timestamped table) | TimescaleDB is the right production answer at real scale; standing one up for a demo is wasted setup time. |
| Object storage | AWS S3 vs MinIO | **MinIO** | Keeps evidence clips fully on-prem, matching the privacy architecture; no cloud account/billing needed. |
| Frontend | React vs Vue vs plain HTML/JS | **React** | Richest component ecosystem for the grid+chart-heavy dashboard (recharts for trend graphs). |

## 12. Deployment target

| Hardware | Fit |
|---|---|
| **NVIDIA Jetson Orin Nano** (production target) | Native TensorRT, runs YOLO11 + BoT-SORT + YOLO11-pose comfortably at 10fps for several camera streams, low power — matches the "no raw video leaves the room" privacy pitch exactly. |
| Consumer RTX GPU (dev/demo machine) | Faster iteration, not what ships in an exam hall — used for development and hackathon demo. |
| CPU-only (fallback) | Viable only with RTMPose + YOLO-nano variants at reduced frame rate. |

## 13. Differentiators beyond baseline PS compliance

1. Per-student baseline calibration (statistical, not flat threshold) — §5.
2. Seat-anchored identity via homography, not appearance re-ID — §3.
3. Multi-camera confidence fusion for occlusion/blind spots — §8.
4. Temporal pattern scoring over isolated single-event alerts — §7.
5. Deterministic template-based explanations, not generative — §10.
6. System health / degraded-coverage awareness — §8.
7. Human-in-the-loop feedback that visibly retunes thresholds live — §10.
8. Cross-venue federated threshold learning: aggregate anonymized
   baseline-deviation statistics (never video/skeletons) across exam halls to
   speed up calibration for new deployments.
9. Adaptive per-student compute budgeting: full-rate inference only for
   currently "warm" (recently flagged) students, throttled rate for calm
   ones — extends effective camera count on fixed hardware.
10. Pre-exam camera coverage validator: automated check via homography that
    every seat falls within at least one camera's field of view, flagging
    blind-spot seats before the exam starts.
11. Post-exam correlation replay: since only structured event logs are
    stored (not raw video), a lightweight offline review mode (PS #2's
    problem) falls out for free on top of the real-time system.

## Reference benchmarks (for accuracy target-setting)

A published system combining pose estimation with YOLO object detection
reported 91.71% accuracy, 90.74% precision, 97.64% recall for exam-cheating
detection — used here as the number to benchmark against, and as
justification for the dual-branch (pose + object) architecture over either
signal alone.

## Accuracy checklist

- Fuse pose + object signals; don't rely on either alone.
- Temporal smoothing (majority vote / exponential smoothing over 15-30
  frames) before triggering an event — never classify on one frame.
- Hard-negative mining: explicitly include stretching, dropping a pen,
  hand-on-chin thinking, glasses adjustment as negatives during training —
  these are the PS's own named false-positive sources.
- Confidence calibration (temperature/Platt scaling) so risk scores are
  meaningful for threshold tuning, not arbitrary.
- Transfer learning throughout, never from-scratch training on the small
  staged dataset.
- Validate test splits by lighting condition and camera angle, not randomly —
  report accuracy per-condition.
