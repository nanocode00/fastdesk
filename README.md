# FastDesk

FastDesk is an experimental low-latency remote desktop project focused on minimizing interactive latency and measuring it reproducibly.

## Initial goal

Build a minimal remote-desktop pipeline and compare its latency under repeatable conditions against existing solutions such as RustDesk and Sunshine/Moonlight.

The first milestone is not a full remote-desktop product. It is a reproducible benchmark harness that can measure visual latency consistently before implementation begins.

## Planned stages

1. Establish reproducible baseline benchmarks.
2. Measure RustDesk and Sunshine/Moonlight under the same conditions.
3. Build a minimal FastDesk streaming prototype.
4. Compare capture, encode, transport, decode, render, and input latency.
5. Optimize the dominant latency sources.
