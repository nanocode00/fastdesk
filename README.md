# FastDesk

FastDesk is an experimental low-latency remote-control project focused on **stable interactive frame delivery to Android clients**.

The project is not tied to a discrete desktop GPU. Windows hosts may use NVENC or other hardware encoders when available, while Android hosts should use the platform hardware codec path through MediaCodec.

## Primary goal

Build and measure a remote streaming path that feels more responsive than general-purpose remote desktop tools in the user's normal Android usage environment.

The first product path is:

```text
Windows host
  -> low-latency capture
  -> hardware encode
  -> direct network transport
  -> Android hardware decode
  -> Surface render
```

The next major path is Android-to-Android:

```text
Android MediaProjection
  -> MediaCodec hardware encode
  -> direct network transport
  -> Android MediaCodec hardware decode
  -> Surface render
```

## Performance direction

The initial engineering target is 1080p60 where both endpoints can sustain it. For interactive workloads, FastDesk should prefer stable frame pacing and low queue depth over maximizing image quality.

Provisional targets for the first Android client prototype:

- 60 fps target stream
- sustained displayed frame rate around 55+ fps under continuous motion
- minimal long frame stalls
- latest-frame-wins behavior when the pipeline falls behind
- hardware encode/decode wherever the platform exposes a suitable path

These are targets to validate with measurements, not assumptions about what every device can sustain.

## Benchmark philosophy

Android user-perceived latency is the primary benchmark.

RustDesk's built-in quality monitor is useful for recording FPS, reported delay, bitrate, and codec state, but its reported delay is treated as an **auxiliary diagnostic**, not the final end-to-end display latency.

The ground-truth comparison should use a high-frame-rate camera that can see both the source display/event and the Android client display. FastDesk will also expose internal timestamps so capture, encode, network, decode, and render-submit latency can be separated.

The existing Windows-to-Windows Python benchmark remains useful as a development and regression tool, but it is no longer the primary product benchmark.

## Current status

- Windows benchmark harness implemented
- RustDesk baseline investigation in progress
- Android-first benchmark plan defined
- streaming prototype not yet implemented

## Project documents

- [Benchmark plan](docs/benchmark-plan.md)
- [Reference architecture](docs/reference-architecture.md)
- [Roadmap](docs/roadmap.md)
- [Windows benchmark harness](benchmark/README.md)

## Development stages

1. Establish Android-focused RustDesk baselines.
2. Validate user-visible latency with an external camera.
3. Build a minimal Windows-to-Android video-only FastDesk path.
4. Instrument capture/encode/network/decode/render timing.
5. Add the low-latency input/control path.
6. Add Android-to-Android capture and hardware encoding.
7. Add capability-based adaptation for weaker devices.
8. Optimize only after the measurements identify the dominant bottlenecks.
