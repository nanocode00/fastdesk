# Roadmap

## Phase 0 — Baseline and measurement

Goal: establish a benchmark that reflects Android user experience.

Tasks:

- record RustDesk quality monitor data in normal usage
- capture both good-condition and noticeably bad-condition sessions
- define repeatable workloads
- perform the first high-frame-rate camera measurement
- keep the Windows Python benchmark as a supplemental regression tool

Exit condition:

- RustDesk has a repeatable Android baseline and a camera-validated latency measurement.

## Phase 1 — Windows -> Android video thin slice

Goal: prove the shortest useful FastDesk video path.

Scope:

```text
Windows capture
-> hardware H.264 encode
-> direct LAN transport
-> Android MediaCodec decode
-> Surface render
```

No clipboard, file transfer, audio, relay, account system, or broad compatibility work yet.

Exit condition:

- continuous motion is visible on Android with stable frame delivery and measurable latency.

## Phase 2 — Instrumentation and frame pacing

Goal: know where every millisecond and dropped frame goes.

Add:

- per-frame IDs
- capture timestamps
- encode-complete timestamps
- send/receive timestamps
- decode timestamps
- render-submit timestamps
- queue / drop counters
- frame-interval summaries

Exit condition:

- an external latency regression can be traced to one or more pipeline stages.

## Phase 3 — Input/control path

Goal: make the prototype interactively usable.

Add:

- Android touch and pointer input
- keyboard input
- low-latency control transport
- input-to-display measurement

Exit condition:

- basic remote desktop interaction works and can be measured end to end.

## Phase 4 — Android -> Android

Goal: remove the dependency on a desktop host.

Host path:

```text
MediaProjection
-> MediaCodec hardware encode
-> transport
```

Client path remains MediaCodec -> Surface.

Add device capability probing and test:

- 1080p60
- 720p60
- lower fallback modes

Exit condition:

- at least one Android host/client pair can sustain an interactive hardware-codec stream.

## Phase 5 — Adaptive policy

Goal: stay responsive across different devices and networks.

Evaluate adaptation of:

- bitrate
- resolution
- FPS
- keyframe policy
- queue depth
- frame dropping

For interactive use, explicitly test FPS-first policies such as 720p60 versus higher-resolution lower-FPS modes.

## Phase 6 — Connectivity and optional relay

Only after the direct path is strong:

- NAT traversal
- relay
- reconnect/session management
- optional accelerator/transcoder
- multi-client support

These features must not silently increase latency on the direct local-network path.

## Current next actions

1. Finish the RustDesk Android baseline.
2. Record a high-latency RustDesk session when it naturally occurs.
3. Build the camera-based synthetic transition test.
4. Start the Windows-to-Android video-only thin slice.
