# Reference architectures

FastDesk should learn from mature projects without attempting to reproduce all of their features.

## Projects to study

### RustDesk

Role in FastDesk research:

- general-purpose remote desktop baseline
- session/control architecture
- input handling
- NAT traversal and relay design for later stages

Repository: https://github.com/rustdesk/rustdesk

### Sunshine + Moonlight

Role in FastDesk research:

- primary low-latency streaming reference
- capture/encode/decode/render pipeline
- hardware codec paths
- frame pacing and interactive input behavior

Repositories:

- https://github.com/LizardByte/Sunshine
- https://github.com/moonlight-stream/moonlight-qt

### Looking Glass

Role in FastDesk research:

- latency-oriented capture and presentation ideas
- minimizing unnecessary copies
- GPU-oriented frame movement

Repository: https://github.com/gnif/LookingGlass

### Selkies

Role in FastDesk research:

- browser-oriented remote streaming
- WebRTC/WebSocket trade-offs
- possible future web/mobile access

Repository: https://github.com/selkies-project/selkies

### Wolf

Role in FastDesk research:

- configurable streaming-server architecture
- Moonlight-compatible streaming ecosystem

Repository: https://github.com/games-on-whales/wolf

## FastDesk initial architecture hypothesis

The minimal path to investigate is:

```text
Host
  capture
    -> hardware encode
      -> latency-oriented transport
        -> client receive
          -> hardware decode
            -> immediate render

Client input
  -> separate low-latency control path
    -> host input injection
```

## Design principles to test, not assume

1. Latest-frame-wins behavior may be preferable to waiting for stale video data.
2. Video and input/control traffic may benefit from different reliability requirements.
3. Buffer depth and presentation scheduling can be as important as codec speed.
4. Avoiding unnecessary CPU/GPU memory copies may materially reduce latency and resource usage.
5. Every optimization should be justified by benchmark data rather than intuition.

## Research task before FastDesk v0

For RustDesk, Sunshine/Moonlight, and Looking Glass, document:

- capture API / method
- encoder path
- transport protocol and reliability behavior
- decoder path
- render/presentation strategy
- input transport
- buffering / queueing behavior
- latency-oriented configuration knobs

Prefer source-code references over marketing documentation.
