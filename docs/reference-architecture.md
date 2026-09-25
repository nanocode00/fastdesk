# Reference architecture

FastDesk should optimize for low latency and stable frame pacing while remaining portable across Windows and Android hosts.

## Architecture principles

1. **Android is a first-class client and host platform.**
2. **Do not depend on a discrete GPU.** Use platform hardware codec blocks when available.
3. **Keep queues shallow.** A stale high-quality frame is often worse than a newer frame.
4. **Prefer latest-frame-wins behavior** when real-time interactivity matters.
5. **Measure each stage** before optimizing it.
6. **Keep video and control paths logically separate** because their reliability and latency needs differ.
7. **Adapt to device capability** instead of assuming every Android device can sustain 1080p60.

## First implementation: Windows host -> Android client

```text
Windows capture
  -> hardware encoder
  -> low-latency transport
  -> Android receive
  -> MediaCodec hardware decoder
  -> Surface
```

### Windows capture

Candidates:

- Windows Graphics Capture
- Desktop Duplication / DXGI

The selected path should minimize copies and expose timestamps useful for profiling.

### Windows encode

Use a hardware encoder when available, such as NVENC on supported NVIDIA systems.

The first implementation should favor a low-latency H.264 path because Android hardware decode support is broad. HEVC can be evaluated later.

Avoid unnecessary buffering and B-frame-heavy configurations when they add presentation delay.

## Android client

The Android client should keep the critical path short:

```text
network receive
  -> compressed access unit
  -> MediaCodec
  -> output Surface
```

Avoid CPU pixel conversion unless required for diagnostics.

Important measurements:

- receive timestamp
- decoder input timestamp
- decoder output timestamp
- render submission timestamp
- dropped / skipped frame counts
- queue depth where observable

## Android host -> Android client

The Android host path should use:

```text
MediaProjection
  -> encoder input Surface
  -> MediaCodec hardware encoder
  -> transport
  -> Android MediaCodec decoder
  -> Surface
```

This path does not require a desktop-class GPU. Its viability depends on the SoC's hardware codec capabilities, capture rate, thermal behavior, and network.

### Capability-based operating modes

Possible initial modes:

| Mode | Intended device | Example target |
| --- | --- | --- |
| Performance | high-end Android | 1080p60 |
| Balanced | mid-range Android | 1080p45-60 or 720p60 |
| Compatibility | constrained Android | 720p30-60 |

The exact policy must be benchmark-driven.

For interactive control, FastDesk should test whether preserving 60 fps at a lower resolution feels better than dropping to 30 fps at a higher resolution.

## Transport

The transport is intentionally not fixed yet.

Candidates include:

- UDP-based custom transport
- QUIC
- another low-latency datagram-oriented design

Requirements:

- direct local-network path when possible
- low head-of-line blocking for video
- explicit handling of loss and stale frames
- separate treatment of input/control traffic
- instrumentation for send/receive timing

Reliability policy should be chosen from measurements rather than copied from a file-transfer protocol.

## Input path

Video-only streaming comes first.

After the video path is stable:

```text
Android touch / keyboard
  -> low-latency control channel
  -> host input injection
```

Android-host input injection has separate permission and platform constraints and should be treated as its own feasibility track.

## Optional accelerator / relay

A stronger PC, server, or Android device may later act as a relay or accelerator, but it should not be required for the direct low-latency path.

A weak Android host still needs to capture and compress its screen before sending it over ordinary Wi-Fi; raw 1080p60 transport is not a practical default.

Useful future relay roles:

- NAT traversal
- multi-client fan-out
- bitrate adaptation
- optional transcoding when the latency cost is acceptable

## Projects to study

### RustDesk

Use as the general-purpose remote-control baseline.

Study:

- Android decode/render path
- video QoS and buffering
- input path
- relay/NAT architecture
- quality monitor metrics

Repository: https://github.com/rustdesk/rustdesk

### Sunshine + Moonlight

Use as the main low-latency streaming reference.

Study:

- capture and encode scheduling
- hardware codec configuration
- frame pacing
- input latency
- Android Moonlight behavior

Repositories:

- https://github.com/LizardByte/Sunshine
- https://github.com/moonlight-stream/moonlight-qt
- https://github.com/moonlight-stream/moonlight-android

### Looking Glass

Study zero-copy and low-copy presentation ideas.

Repository: https://github.com/gnif/LookingGlass

### Selkies

Study browser/WebRTC trade-offs for possible future clients.

Repository: https://github.com/selkies-project/selkies

### Wolf

Study configurable streaming-server and Moonlight-compatible architecture.

Repository: https://github.com/games-on-whales/wolf

## Questions to answer with prototypes

Before committing to a production architecture, measure:

- capture API latency and consistency
- encoder latency
- effect of encoder buffer depth
- transport loss behavior
- Android decoder queue behavior
- render/presentation queue depth
- 1080p60 sustainability
- 720p60 versus 1080p30/45 trade-offs
- thermal throttling over longer sessions
