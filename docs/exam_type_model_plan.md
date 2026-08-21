# Exam-Type-Specific Behavior Model — Tier 2 Design Plan

**Status:** roadmap / not built. Tier 1 (a hand-tuned weight-profile switch,
`risk_engine/scorer.py`'s `EXAM_TYPE_PROFILES`) is real and shipped today.
This document specifies what a fully data-driven version would look like —
specific enough to actually start executing, not presentation filler.

## 1. Why Tier 1 isn't the final answer

Tier 1 encodes a *hypothesis* — "MCQ marking is brief/periodic, so sustained
hand motion is more anomalous there than in a written exam" — as five
hand-picked numbers per exam type. That hypothesis is reasonable (it's the
same reasoning docs/architecture.md already uses to justify torso-proxy over
raw pixel motion), but it's still a guess, not a measurement. Tier 2 replaces
the guess with weights *learned* from labeled examples of what normal and
abnormal behavior actually look like in each exam context — because "normal"
itself is exam-type-dependent, not just "misconduct."

## 2. What labeled data is needed

Two axes, not one: **exam type** (MCQ / Written) × **behavior class**
(normal / misconduct-in-progress). Four staged footage sets, minimum:

| Set | What it captures |
|---|---|
| MCQ — normal | Students marking answers: brief periodic hand movement toward the answer sheet, occasional posture shifts, glances at the question paper (not a neighbor) |
| MCQ — misconduct | Sustained/repeated hand movement inconsistent with marking, neighbor-directed glances, phone-check gestures |
| Written — normal | Near-continuous writing hand motion, occasional pauses/thinking posture, page-turning |
| Written — misconduct | Paper/chit passing, sustained neighbor-directed head turn, hand-to-desk-object reach inconsistent with normal writing |

Each set needs multiple *students* (body-type/handedness variety) and
multiple *sessions* (lighting/camera-angle variety) — a single student in a
single sitting isn't enough to generalize, per the same reasoning
docs/architecture.md already applies to the phone detector (a single
overfit run false-positived on a chair from too little data).

## 3. Roughly how much data per class

Following this project's own established precedent rather than a generic
rule of thumb:

- **phone_detector_v1** (already built, this codebase): 69 training images
  was demonstrably **too small** — it overfit and false-positived on a
  chair (docs/build_order.md). The v2 retrain effort already underway
  collected **405 candidate frames** for labeling as the next attempt at
  that same single-class detection problem.
- **ST-GCN++** (docs/architecture.md §6): explicitly warns against training
  "from zero on a few hundred clips — it will overfit," and instead
  specifies fine-tuning from NTU RGB+D pretrained weights (56,880 skeleton
  sequences, 60 classes) on a **small** labeled clip set of exam-specific
  behaviors.

Applying that same fine-tuning-not-from-zero approach, per exam-type ×
behavior-class cell (8 cells total: 2 exam types × 2 behavior classes ×
roughly normal/misconduct split, though normal classes need proportionally
more since they must cover more natural variation):

- **Normal-behavior classes**: 150–250 clips each (roughly 2–4× the phone
  detector's 69-image floor that proved too small, since a *behavior
  sequence* has more natural variation than a static object crop) —
  ~500–1,000 total across MCQ-normal + Written-normal.
- **Misconduct classes**: 75–150 clips each — genuine misconduct is rarer
  to stage/collect (needs actors, IRB-adjacent consent considerations for a
  real deployment) but the classification target is narrower (a handful of
  named behaviors, not open-ended "normal").
- **Total realistic target: ~1,200–1,800 labeled clips** across all four
  sets, each clip a few seconds of skeleton sequence (already reduced to
  17-point COCO pose by this pipeline before labeling — no raw video needs
  to leave the edge boundary for labeling either, consistent with the
  privacy design already in place).

This is meaningfully more than the 405-frame v2 phone-detector effort, but
in the same order of magnitude — not a 56,880-sequence NTU-scale undertaking,
because fine-tuning from NTU-pretrained ST-GCN++ weights (already the
project's stated plan) means this dataset only needs to teach the model the
*exam-specific* delta, not general human motion from scratch.

## 4. How this integrates with Tier 1 — replace, not layer

Tier 2 should **replace** Tier 1's hand-tuned weights per exam type, not run
alongside them as a second system feeding the same risk score:

1. Train (or fine-tune) one ST-GCN++ model per exam type — `mcq_behavior.pt`
   and `written_behavior.pt` — each classifying a skeleton sequence into the
   named behavior classes for that exam type (normal / sustained-hand /
   neighbor-glance / object-reach / etc.), exactly the "hybrid" architecture
   docs/architecture.md §6 already specifies, just specialized per exam type
   instead of one model for all contexts.
2. `RiskEngine.apply_profile(exam_type)` (already built, Tier 1) becomes the
   loading point for the exam-type-specific model instead of a weight dict —
   same call site, same "select exam type → everything downstream adapts"
   contract the UI already has, so **no frontend change is needed** when
   Tier 2 ships.
3. The model's per-class confidence scores get combined into `risk_score`
   the same way ST-GCN++ confidence was always planned to combine with
   rule-based z-scores and object detection (docs/architecture.md §7's
   weighted sum) — Tier 1's five weights get replaced by the model's own
   learned decision boundary, with the rule-based z-score/pattern/object
   signals still running in parallel as the fallback and explanation source
   (never removed — docs/architecture.md §6 is explicit that rule-based
   stays even after ST-GCN++ exists, for exactly this explainability
   reason).
4. Tier 1's hand-tuned weights don't disappear when Tier 2 ships — they
   become the **fallback profile** for an exam type that doesn't have
   enough labeled data yet (e.g., a third exam format added later), the
   same relationship rule-based scoring already has with ST-GCN++ generally.

## 5. Realistic effort estimate, stated honestly

| Phase | Effort | Notes |
|---|---|---|
| Staging + collecting ~1,200–1,800 clips | 3–5 days of active filming/staging, spread over more like 2–3 weeks of scheduling (needs multiple students, multiple sessions, ideally multiple rooms for camera-angle variety — same generalization concern Part 1's multi-video audit already surfaced) | Largest real bottleneck; this project has no existing exam-behavior dataset today, per this task's own framing |
| Labeling | 1–2 weeks, using the same Roboflow-based workflow already in use for the phone detector (`idibag/kinesis-ai-contraband` project) | Behavior-sequence labeling (marking a time range + class) is slower per-clip than the phone detector's per-frame bounding boxes |
| Custom skeleton layout in `pyskl/utils/graph.py` | 1–2 days | One-time engineering cost, needed regardless of exam-type specialization (COCO 17-point vs NTU's 25-point Kinect layout) — see docs/architecture.md §6 |
| Fine-tuning + validation per exam type | 2–4 days per exam type (GPU time is cheap relative to the data-collection bottleneck above) | Validate the same way this project already validates everything: real before/after false-positive/negative numbers on held-out real footage, not just training-loss curves |
| **Total: roughly 4–8 weeks elapsed**, dominated by data collection/labeling, not model training | | Consistent with why this project chose the Tier 1 hand-tuned approach as the thing to ship *today* — it needs zero new data and is real, working, and honest about being hand-tuned rather than learned |

## 6. What NOT to do

Do not train ST-GCN++ from zero on whatever the first data-collection pass
produces "just to have a model" — docs/architecture.md §6's own explicit
warning ("train from zero on a few hundred clips, it will overfit")
applies exactly as much per-exam-type as it does to the general case. If
data collection stalls short of the ~1,200–1,800 clip target, keep Tier 1's
hand-tuned profiles in production rather than shipping an undertrained
model — an honest hand-tuned weight beats a confidently-wrong learned one,
the same principle this project already applies to phone_detector_v1's
"experimental" tagging.
