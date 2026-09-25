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

## Files

- `host_agent.py`: Windows host pattern window + TCP control server.
- `benchmark_client.py`: Windows client screen capture, transition detection, CSV output, and percentile report.
- `core.py`: dependency-free detection/statistics helpers.
- `requirements.txt`: client-side Python dependencies.
- `tests/`: logic tests that can run without a GUI or screen capture.

## Recommended layout

Keep normal development clones in WSL if desired, but run the actual benchmark with **native Windows Python** on both computers. The benchmark needs to observe the real Windows RustDesk/Moonlight window and show the target directly on the Windows host desktop.

Using separate Windows clones also avoids mixing WSL and Windows virtual environments:

```text
Laptop
  WSL      ~/fastdesk            development clone
  Windows  C:\dev\fastdesk      benchmark client runtime

Desktop
  WSL      ~/fastdesk            development/C2C clone
  Windows  C:\dev\fastdesk      host-agent runtime
```

## Windows setup

On both computers, open PowerShell:

```powershell
git clone https://github.com/nanocode00/fastdesk.git C:\dev\fastdesk
cd C:\dev\fastdesk
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r benchmark\requirements.txt
```

`tkinter` is included with the normal Python.org Windows installer. The client installs both capture backends:

- `dxcam` (default): uses Windows Graphics Capture (`winrt`) by default.
- `dxcam --dxcam-api dxgi`: Desktop Duplication fallback for DXcam.
- `mss`: final fallback via `--capture-backend mss`.

The host does not need the capture packages at runtime, but installing the same requirements on both machines keeps setup simple.

## 1. Start the desktop host agent

On the Windows desktop:

```powershell
cd C:\dev\fastdesk
.\.venv\Scripts\Activate.ps1
python benchmark\host_agent.py --port 8765
```

The program opens a fullscreen black/white target. Press **Esc** to close it.

For setup, a window is easier to position:

```powershell
python benchmark\host_agent.py --port 8765 --windowed
```

Allow Python through Windows Firewall on the private network if Windows prompts. Note the desktop's LAN IPv4 address with `ipconfig`.

The v1 host agent has no authentication because it only exposes the benchmark toggle control. Bind/use it only on a trusted LAN or similarly private test network; do not expose port 8765 to the public Internet.

## 2. Open the remote desktop session

From the laptop, connect to the desktop with RustDesk (or another implementation being tested). Keep scaling, resolution, codec settings, and display refresh rate fixed across products.

The target area must be visible inside the remote desktop window.

## 3. Choose the laptop capture ROI

`--roi` uses **physical Windows screen coordinates** on the laptop:

```text
LEFT,TOP,WIDTH,HEIGHT
```

Pick a rectangle well inside the black/white target and avoid RustDesk borders, toolbars, text, or the mouse cursor. A large uniform region such as 400x300 is sufficient.

Example:

```text
--roi 600,350,400,300
```

The first run prints the initial mean luminance. A black target should normally be below the default black threshold (80), and a white target should normally be above the default white threshold (175). Override the thresholds if video range, HDR, or scaling changes those values.

## 4. Run the laptop benchmark client

On the Windows laptop, replacing `192.168.0.10` and the ROI with your values:

```powershell
cd C:\dev\fastdesk
.\.venv\Scripts\Activate.ps1
python benchmark\benchmark_client.py `
  --host 192.168.0.10 `
  --port 8765 `
  --roi 600,350,400,300 `
  --warmup 10 `
  --samples 100 `
  --output benchmark\results\rustdesk-lan-1080p60.csv
```

DXcam with the WinRT/Windows Graphics Capture API is the default capture path. Before a full benchmark, verify that the ROI actually sees the remote black/white transitions:

```powershell
python benchmark\benchmark_client.py `
  --host 192.168.0.10 `
  --port 8765 `
  --roi 600,350,400,300 `
  --diagnose-capture
```

Diagnostic mode toggles the host four times and prints the live ROI mean luminance. A healthy run should alternate between values below the black threshold and above the white threshold.

To compare against the older Desktop Duplication path, use:

```powershell
python benchmark\benchmark_client.py `
  --host 192.168.0.10 `
  --port 8765 `
  --roi 600,350,400,300 `
  --dxcam-api dxgi `
  --diagnose-capture
```

If DXcam is unavailable or incompatible on a machine, use the MSS fallback:

```powershell
python benchmark\benchmark_client.py `
  --host 192.168.0.10 `
  --port 8765 `
  --roi 600,350,400,300 `
  --capture-backend mss `
  --warmup 2 `
  --samples 5
```

Useful tuning flags:

```text
--black-threshold 80
--white-threshold 175
--debounce-frames 2
--visual-timeout 2
--interval-ms 150
--jitter-ms 40
--capture-interval-ms 0
--capture-backend dxcam
--dxcam-api winrt
--dxcam-output-idx 0
```

`--capture-interval-ms 0` samples as fast as the selected backend allows. If CPU use is excessive, try 1-4 ms.

## Output

Each measured event stores:

- `event_id`
- `status`
- `target_state`
- `request_sent_ns`
- `ack_received_ns`
- `screen_detected_ns`
- `request_to_ack_ms`
- `ack_to_screen_ms`
- `request_to_screen_ms`

The console prints min/max/mean/stddev plus p50/p90/p95/p99 for each latency metric.

`ack_to_screen_ms` can theoretically be slightly negative if the remote video update reaches the laptop before the TCP ACK does. Keep `request_to_screen_ms` as the end-to-end software comparison metric as well.

If the requested visual transition is not detected, the sample is explicitly marked `timeout`; latency values are left empty rather than fabricating a measurement. If the ROI was not visibly in the opposite color immediately before a toggle, it is marked `baseline_mismatch` instead. This guards against accidentally measuring a toolbar or another static bright/dark area as zero latency.

Any non-`ok` measured sample makes the client exit non-zero after writing the CSV.

## Run logic tests

These tests do not require a GUI, RustDesk, `mss`, or `numpy`:

```powershell
python benchmark\tests\run_tests.py
```
