# Part 0.5 — Ingestion / real-CCTV readiness (2026-08-21)

Everything built before this pass was tested against video files read
directly — never against genuine RTSP conditions (network jitter,
reconnects, real-time pacing). This document records what changed when it
actually was.

## Setup

- `ffmpeg` (Gyan.FFmpeg full build, installed via winget) pushing
  `data/test_videos/04.CCTV Candidate Talking.mkv` with `-re -stream_loop -1`
  (real-time pacing, looped indefinitely) over TCP into...
- `mediamtx` v1.20.1 (`tools/mediamtx/`), a lightweight local RTSP server,
  serving it back out at `rtsp://127.0.0.1:8554/kinesis_test`.
- `ingestion/video_source.py`'s `VideoSource` pointed at that URL exactly as
  it would point at a real camera — no file-mode special-casing, same code
  path.

## Findings

**1. Duration-based logic under real-time pacing: correct, and this was
the first time it was actually tested this way.** Direct file reads (every
prior test in this project, including the whole multi-video audit two
sessions ago) decode at ~1,600fps — effectively unthrottled — while
`sim_time` in `pipeline_worker.py` is wall-clock-based (`time.time() -
start_wall_time`) regardless of source. That combination means file-mode
testing was *never* actually exercising the settling-window/sustained-event
timing logic against real elapsed time relative to real frame delivery —
it was exercising wall-clock timing against an artificially frame-rich
video that raced through cameras in-memory. Against genuine RTSP,
throttled to the source's real 8fps: calibration completed within the
configured 20s settling window, real alerts fired, and the new
calibration-quality safeguard (Part 2.5) fired correctly too. This is the
first real confirmation the timing logic holds under conditions a real
camera would actually produce.

**2. Real found-and-fixed bug: an uncaught `cv2.error` could silently kill
ingestion with zero reconnect attempts.** Simulating a network stall
(suspending the RTSP publisher process mid-stream, resuming it later) hit
this directly: `self._cap.read()` doesn't always fail cleanly with
`ok=False` — under a stall it can throw a raw `cv2.error` instead, which
bypassed the `if not ok: reconnect()` path entirely and killed the ingestion
thread outright, no retry, no log line, nothing. Reproduced 1-in-3 stall
attempts. **Fixed** in `ingestion/video_source.py`: `.read()` is now wrapped
in `try/except cv2.error`, routing into the same reconnect path as a clean
failed read. Re-ran the same stall test 3x after the fix — the exception
fired again on one run and was caught and recovered from correctly.

**3. Reconnect works, but recovery latency is dominated by an OpenCV/FFmpeg
internal timeout, not the configured `reconnect_delay_s`.** Killing
`mediamtx` outright (not just stalling it) confirmed `VideoSource` never
crashes while the server is down — it sits retrying, exactly as designed.
But once the server came back, the first recovered frame arrived **~27
seconds** after restart, not the ~2s `reconnect_delay_s=2.0` implies.
Root cause: `cv2.VideoCapture()`'s constructor itself blocks for FFmpeg's
own internal ~30s socket-open timeout *before* our retry loop gets a turn —
so real recovery latency after a genuine outage is `~30s + reconnect_delay_s`,
not `reconnect_delay_s` alone. **Attempted fix**: passed `stimeout`/
`rw_timeout` via `OPENCV_FFMPEG_CAPTURE_OPTIONS` (the same mechanism used
for `rtsp_transport;tcp`) to shorten this. Tested twice — did not measurably
reduce the timeout on this OpenCV 5.0/FFmpeg 9.0 build. Left the option
string in (`ingestion/video_source.py`, harmless, may work on other
builds), but **this is not actually fixed** — recovery after a real outage
should be assumed to take up to ~30s, not ~2s, until someone either finds
the right FFmpeg build/option combination or wraps the `VideoCapture()`
constructor call in a hard-timeout watcher thread (real fix, bigger lift —
see effort table below).

**4. Buffer=1 drop-latest policy holds correctly.** After both the outright
kill/restart and the stall/resume tests, frame delivery resumed at the
source's real cadence (~110-220ms between frames) with no burst of stale
queued frames — confirming a network hiccup doesn't turn into a cascading
delay or a dump of backlog once the connection returns.

**5. Effective end-to-end throughput under real RTSP pacing: ~6.7fps for a
single 640×480@8fps camera, below the source's own native rate.** Running
the *full* pipeline (pose + calibration + gesture + risk scoring, not just
raw frame reads) against the RTSP stream for 75s processed 500 frames
(6.67fps), while the raw `VideoSource` alone (no ML in the loop) sustained
~8fps matching the source. The gap is real GPU/CPU processing time per
frame becoming the bottleneck relative to real-time delivery — a genuine
capacity number, not visible in any prior file-mode test (which never had
to keep pace with anything). Worth factoring into how many camera groups
one GPU can realistically run concurrently — this session's multi-worker
architecture (one `PipelineWorker` per seat-overlap group) means N cameras
= N independent full pipelines competing for the same GPU.

**6. Soak test**: launched against the same RTSP stream, sampling RSS/GPU
memory/DB growth every 60s (`tools/soak_test.py` → `tools/soak_test_
results.csv`). Results through the first 28 minutes (continuing in the
background past this document being written — a genuine multi-hour run
takes multi-hours, so this is a real partial result, not a guaranteed
final number):

| Metric | Result |
|---|---|
| RSS (process memory) | Peaked ~1.65GB during model-load warmup, settled to a stable 577-635MB band by minute 5 and stayed there through minute 28 — no growth trend |
| GPU memory | Flat at 53MB the entire run, zero drift |
| Frame throughput | ~470 frames/min (~7.8fps), consistent minute to minute |
| DB/event growth | Growing steadily and linearly with elapsed time (expected — no sign of unbounded accumulation or a leak in the event pipeline) |
| Crashes/errors | Zero over 28 minutes |

No memory-leak signal in the portion actually observed. This is not the
same as a validated 2-3hr claim — the settling-window/baseline-drift
question specifically ("do baselines stay sane over a realistic full exam
duration") needs the calibration to run through several natural recalcs
or an intentionally longer window than tested here to say anything past
"the first baseline computed correctly and nothing degraded obviously in
28 minutes."

## Real-world integration gaps (documented, not fixed this pass)

| Gap | Effort to close |
|---|---|
| Vendor-specific RTSP URL patterns (Hikvision/Dahua/Axis each have different path conventions, ONVIF profile quirks) beyond manual config entry | Small — a lookup table of common vendor URL templates + a "test connection" button in setup; a few hours |
| NVR-channel compatibility (multiple concurrent RTSP consumers pulling one channel — most consumer NVRs cap concurrent stream pulls per channel) | Medium — needs either NVR-side substream configuration guidance or a local re-streaming proxy (mediamtx itself could serve this role) so only one real connection is made per camera; a day or two, plus needs real NVR hardware to validate against, not just this session's software simulation |
| H.265/HEVC alongside H.264 | Small on the decode side — OpenCV's FFmpeg backend already handles HEVC transparently (same code path, no special-casing needed, confirmed by this session's ffmpeg build supporting it); the real cost is GPU decode performance validation on the actual Jetson Orin Nano target, which wasn't available to test in this session |
| Lens-undistortion preprocessing for wide-angle/fisheye mounts | Medium — `cv2.fisheye`/`cv2.undistort` exist and are well-trodden, but produces useless results without a real per-lens calibration (checkerboard capture), which needs the actual mounted hardware, not a video file; this session's video 12 test (wide/fisheye-looking angle) worked without undistortion because seat-anchoring's homography absorbs *planar* perspective distortion, but true fisheye barrel distortion is non-planar and homography alone won't fully correct it at the frame edges |
| NTP time sync across multiple camera sources (for evidence/fusion timestamp accuracy) | Small for a single-site deployment (point every camera device at the same local NTP server — an infra/deployment step, not a code change); becomes a real engineering problem only for a genuinely distributed multi-site rollout, which is out of scope for this system's current single-exam-hall design |

## What this validates vs. doesn't

**Validates**: the ingestion layer's core promises (TCP transport, buffer=1
drop-latest, no crash on outage, eventual auto-reconnect, real-time-correct
duration logic) hold up against a genuine, real-time-paced RTSP source, not
just a file read masquerading as one. One real robustness bug was found and
fixed in the process — a clear net positive for having actually run this
test rather than assuming file-mode testing was representative.

**Doesn't validate**: real camera hardware (see "one genuine non-simulated
camera" below), real network conditions beyond a local-loopback simulation
(no real jitter/latency/packet corruption — `tc` isn't available on this
Windows machine without WSL, which isn't installed; the stall/resume test
via process-suspend is a reasonable proxy for "frames stop arriving" but
not for actual packet loss/corruption mid-frame), or multi-camera concurrent
GPU load (the throughput number above is for one camera; this session's
multi-worker architecture makes N-camera GPU contention untested).
