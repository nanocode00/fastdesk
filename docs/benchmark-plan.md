# Benchmark plan

## Status

This document defines the **v2 Android-first benchmark plan**.

The earlier Windows-to-Windows automated benchmark is still maintained under `benchmark/`, but it is now a supplemental regression tool rather than the primary FastDesk performance metric.

## Objective

Answer two questions with repeatable evidence:

1. How responsive is RustDesk in the user's normal Android environment?
2. Does FastDesk reduce user-visible latency and improve frame pacing under the same conditions?

The benchmark must distinguish between:

- transport / stream queue state
- delivered and displayed frame rate
- actual user-visible end-to-end latency
- internal FastDesk pipeline latency

## Primary environments

### Phase A: Windows host -> Android client

This is the first FastDesk implementation and comparison environment.

Record for every run:

- Windows host hardware and OS
- Android device model and OS
- Android display refresh rate
- network type and access point
- resolution and target FPS
- codec
- hardware encode/decode state
- application versions
- power / thermal conditions when relevant

### Phase B: Android host -> Android client

This becomes the portability test once the Windows-to-Android thin slice is stable.

The Android host should use MediaProjection and a hardware MediaCodec encoder when supported. The benchmark must not assume access to a discrete GPU.

## Ground-truth latency measurement

The primary end-to-end latency measurement is an external high-frame-rate camera that sees both:

1. the source-side visual event
2. the Android client's displayed result

A frame difference gives the observed display latency without requiring synchronized clocks.

Examples:

- 120 fps camera: about 8.33 ms per camera frame
- 240 fps camera: about 4.17 ms per camera frame

Use multiple events per run and summarize the distribution rather than relying on one transition.

## RustDesk baseline

Enable RustDesk's quality monitor on Android and record:

- reported FPS
- reported Delay
- bitrate / speed
- codec
- hardware decode setting if visible
- subjective responsiveness notes

Treat RustDesk `Delay` as an auxiliary stream diagnostic. Do **not** equate it directly with source-to-photon or input-to-photon latency.

### Workloads

Use at least these workloads:

1. **Idle/static** — verifies steady-state behavior.
2. **Window drag / continuous UI motion** — interactive motion workload.
3. **Fast scrolling** — stresses update frequency and frame pacing.
4. **60 fps motion content** — stresses sustained capture/encode/decode/render.
5. **Synthetic visual transition** — provides precise camera-measurement events.

For the first baseline pass, 30 seconds per workload is sufficient. Repeat representative runs at least three times when comparing implementations.

## Metrics

### Primary

- external-camera display latency: p50 / p95 / p99 when sample count permits
- displayed/delivered FPS
- frame interval distribution
- p95 frame interval
- count of visible long stalls (initially >50 ms)

### RustDesk auxiliary metrics

- quality monitor Delay
- quality monitor FPS
- bitrate / speed
- codec

### FastDesk internal telemetry

FastDesk should timestamp at least:

```text
capture start / frame acquired
encode complete
packet send
Android receive
decode complete
render submit
```

This allows the pipeline to be decomposed into capture, encode, network, decode, and render-queue components.

The final display step still requires external validation because render submission is not the same as the pixel becoming visible.

## Provisional performance targets

For a capable Windows host and Android client on a good local network:

- target stream: 1920x1080 at 60 fps
- sustained motion: approximately 55+ displayed fps
- avoid persistent multi-frame buffering
- minimize >50 ms frame stalls
- lower external-camera latency than the RustDesk baseline under the same test conditions

These are engineering targets and may be revised after the first controlled baseline.

## Experimental controls

Keep the following fixed within an A/B comparison:

- same host and Android device
- same network path
- same resolution
- same display refresh rate
- same workload
- same camera setup
- similar thermal state
- similar background load

Do not compare a tuned FastDesk run against a RustDesk run captured under materially different network or thermal conditions.

## Windows automated harness

The Python harness in `benchmark/` is useful for:

- development smoke tests
- Windows client regression tests
- validating the host toggle protocol
- testing transition-detection logic

It is **not** the final Android benchmark.

The current client captures a screen ROI. Therefore the target region must be visible and unobscured on the client display; changing window placement or covering the target can invalidate a run. Future tooling may replace this with window-bound capture and a preview/snapshot step.

## Benchmark milestone exit criteria

The benchmark milestone is complete when:

1. a RustDesk Android baseline is recorded under defined workloads;
2. at least one external-camera latency run is repeatable;
3. the same procedure can be applied to FastDesk without changing the metric definition;
4. FastDesk internal telemetry can be correlated with the external result.
