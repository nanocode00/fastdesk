# FastDesk benchmark harness

This directory will contain the reproducible latency benchmark used before and during FastDesk development.

## First benchmark target

Measure visual update latency from a Windows laptop running a remote-desktop client to a Windows desktop host on the same LAN.

The initial implementation will use two small Python programs:

- `host_agent.py`: runs on the controlled desktop and toggles a large high-contrast test region on request.
- `benchmark_client.py`: runs on the laptop, sends test events, observes the remote-desktop window, and records when the visual change becomes visible.

## Why this design

The benchmark is primarily for repeatable A/B comparison rather than laboratory-grade photon-to-photon measurement.

The client should use one monotonic clock (`time.perf_counter_ns()`) for request, acknowledgement, and visual detection timing so that wall-clock synchronization between the two computers is not required.

## Primary measurements

For each event:

- event ID
- request sent timestamp
- host ACK received timestamp
- remote visual change detected timestamp
- request-to-ACK latency
- ACK-to-screen latency
- request-to-screen latency

Aggregate output should include:

- sample count
- minimum / maximum
- mean / standard deviation
- p50 / p90 / p95 / p99

## Baseline order

1. RustDesk
2. Sunshine + Moonlight
3. FastDesk prototypes

All products should be tested with the same machine pair, network, resolution, refresh-rate target, test content, and sampling procedure.
