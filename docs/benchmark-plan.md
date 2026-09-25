# Benchmark plan

## Objective

Create a repeatable baseline that answers one question:

> Is FastDesk measurably more responsive than the alternatives under the same conditions?

The first benchmark should optimize for consistency and automation. External high-speed camera measurements can later be used to validate the automated method.

## Initial environment

- Host: Windows desktop
- Client: Windows laptop
- Network: same LAN for the first baseline
- Initial resolution target: 1920x1080
- Initial refresh target: 60 Hz where supported

Record exact hardware, display refresh rates, network type, codec settings, and application versions with each benchmark run.

## Measurement model

The laptop controls the test.

1. Client sends a `TOGGLE <event_id>` request.
2. Host changes a large high-contrast region immediately.
3. Host returns an ACK containing the same event ID.
4. Client continuously captures a configured region of the remote-desktop window.
5. Client detects the corresponding luminance transition.
6. Client records all timestamps using `time.perf_counter_ns()`.

The primary comparative metric is:

`visual_delay_ms = screen_detected - ack_received`

Also retain `request_to_screen_ms` because it captures control-path overhead as well.

## Detection requirements

The implementation should:

- avoid OCR
- use mean luminance or a similarly cheap pixel statistic
- allow the capture rectangle to be configured
- calibrate black/white thresholds before a run or accept explicit thresholds
- debounce transitions to avoid false positives
- ignore stale/out-of-order event observations
- warm up before collecting samples
- support at least 100 measured events per run
- add configurable timing jitter between events so samples do not accidentally align with a fixed refresh cadence

## Test scenarios

Run each remote-desktop implementation under at least these conditions:

### A. Synthetic toggle
Primary automated latency benchmark.

### B. Desktop interaction
Continuous mouse motion, window dragging, scrolling, and text cursor movement.

### C. Motion content
Video or animation used to observe frame pacing, bitrate behavior, and dropped frames.

The synthetic toggle is the numerical baseline. B and C are complementary workload tests.

## Metrics

### Latency

- request-to-ACK: p50 / p95 / p99
- ACK-to-screen: p50 / p95 / p99
- request-to-screen: p50 / p95 / p99
- min / max / mean / standard deviation

### Resource usage

Later iterations should capture:

- host CPU
- host GPU encode utilization
- client CPU
- client GPU decode utilization
- network throughput
- observed FPS / frame drops where accessible

## Comparison matrix

| Implementation | Codec/settings | p50 visual | p95 visual | p99 visual | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| RustDesk | TBD | TBD | TBD | TBD | baseline |
| Sunshine/Moonlight | TBD | TBD | TBD | TBD | low-latency reference |
| FastDesk v0 | TBD | TBD | TBD | TBD | implementation target |

## Validation

After the automated benchmark is working, validate several runs using a high-frame-rate camera that simultaneously sees the host display and client display.

The camera test is a cross-check, not the primary day-to-day benchmark.

## Success criterion for the benchmark milestone

The milestone is complete when the same benchmark command can produce comparable CSV results and percentile summaries for at least RustDesk and Sunshine/Moonlight without changing the measurement algorithm.
