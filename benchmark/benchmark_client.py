from __future__ import annotations

import argparse
import csv
import json
import random
import socket
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import mss
import numpy as np

from core import (
    BLACK,
    WHITE,
    LuminanceSample,
    classify_luminance,
    find_stable_transition,
    parse_roi,
    summarize,
)


@dataclass
class BenchmarkRow:
    event_id: int
    status: str
    target_state: int
    request_sent_ns: int
    ack_received_ns: int
    screen_detected_ns: int | None
    request_to_ack_ms: float
    ack_to_screen_ms: float | None
    request_to_screen_ms: float | None


class ScreenSampler:
    def __init__(
        self,
        roi: tuple[int, int, int, int],
        *,
        capture_backend: str,
        capture_interval_ms: float,
        history_seconds: float,
        dxcam_output_idx: int,
    ) -> None:
        self.roi = roi
        self.capture_backend = capture_backend
        self.capture_interval_s = capture_interval_ms / 1000.0
        self.dxcam_output_idx = dxcam_output_idx
        # Fast capture can generate many samples. This cap is intentionally generous.
        max_samples = max(2_000, int(history_seconds * 2_000))
        self.samples: deque[LuminanceSample] = deque(maxlen=max_samples)
        self.recent_samples: deque[LuminanceSample] = deque(maxlen=64)
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.error: Exception | None = None

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2.0)

    def wait_until_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        with self.condition:
            while not self.samples and self.error is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("screen capture did not produce any samples")
                self.condition.wait(remaining)
            if self.error is not None:
                raise RuntimeError(f"screen capture failed: {self.error}") from self.error

    def wait_for_state(
        self,
        *,
        target_state: int,
        after_ns: int,
        black_threshold: float,
        white_threshold: float,
        debounce_frames: int,
        timeout: float,
    ) -> int | None:
        deadline = time.monotonic() + timeout

        with self.condition:
            # The transition may already have arrived through the remote-video
            # path before the TCP ACK reaches us, so inspect buffered history
            # once. Afterwards only inspect a tiny recent window to avoid
            # repeatedly scanning thousands of samples and perturbing the
            # benchmark with unnecessary client CPU work.
            detected = find_stable_transition(
                tuple(self.samples),
                target_state=target_state,
                after_ns=after_ns,
                black_threshold=black_threshold,
                white_threshold=white_threshold,
                debounce_frames=debounce_frames,
            )
            if detected is not None:
                return detected

            while True:
                if self.error is not None:
                    raise RuntimeError(f"screen capture failed: {self.error}") from self.error

                detected = find_stable_transition(
                    tuple(self.recent_samples),
                    target_state=target_state,
                    after_ns=after_ns,
                    black_threshold=black_threshold,
                    white_threshold=white_threshold,
                    debounce_frames=debounce_frames,
                )
                if detected is not None:
                    return detected

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.condition.wait(min(remaining, 0.05))

    def latest_mean(self) -> float | None:
        with self.condition:
            if not self.samples:
                return None
            return self.samples[-1].mean_luminance

    def latest_sample(self) -> LuminanceSample | None:
        with self.condition:
            if not self.samples:
                return None
            return self.samples[-1]

    def _run(self) -> None:
        try:
            if self.capture_backend == "dxcam":
                self._run_dxcam()
            else:
                self._run_mss()
        except Exception as exc:  # pragma: no cover - environment-specific capture failure
            with self.condition:
                self.error = exc
                self.condition.notify_all()

    def _record_frame(self, frame: np.ndarray) -> None:
        mean_luminance = float(np.asarray(frame, dtype=np.uint8)[:, :, :3].mean())
        sample = LuminanceSample(
            timestamp_ns=time.perf_counter_ns(),
            mean_luminance=mean_luminance,
        )
        with self.condition:
            self.samples.append(sample)
            self.recent_samples.append(sample)
            self.condition.notify_all()

    def _run_dxcam(self) -> None:
        try:
            import dxcam
        except ImportError as exc:
            raise RuntimeError(
                "DXcam backend requested but dxcam is not installed; "
                "run: pip install -r benchmark\\requirements.txt"
            ) from exc

        left, top, width, height = self.roi
        region = (left, top, left + width, top + height)
        with dxcam.create(
            output_idx=self.dxcam_output_idx,
            backend="dxgi",
            processor_backend="numpy",
            output_color="BGR",
        ) as camera:
            while not self.stop_event.is_set():
                frame = camera.grab(region=region, new_frame_only=False)
                if frame is not None:
                    self._record_frame(frame)
                if self.capture_interval_s > 0:
                    self.stop_event.wait(self.capture_interval_s)

    def _run_mss(self) -> None:
        left, top, width, height = self.roi
        monitor = {"left": left, "top": top, "width": width, "height": height}
        capture_cls = getattr(mss, "MSS", None)
        capture_context = capture_cls() if capture_cls is not None else mss.mss()
        with capture_context as capture:
            while not self.stop_event.is_set():
                frame = np.asarray(capture.grab(monitor), dtype=np.uint8)
                self._record_frame(frame)
                if self.capture_interval_s > 0:
                    self.stop_event.wait(self.capture_interval_s)


class ControlClient:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.socket = socket.create_connection((host, port), timeout=timeout)
        self.socket.settimeout(timeout)
        self.reader = self.socket.makefile("r", encoding="utf-8", newline="\n")
        self.writer = self.socket.makefile("w", encoding="utf-8", newline="\n")

    def close(self) -> None:
        try:
            self.reader.close()
            self.writer.close()
        finally:
            self.socket.close()

    def toggle(self, event_id: int) -> tuple[int, int, int]:
        request_sent_ns = time.perf_counter_ns()
        self._send({"type": "toggle", "event_id": event_id})
        response = self._receive()
        ack_received_ns = time.perf_counter_ns()

        if response.get("type") == "error":
            raise RuntimeError(
                f"host rejected event {event_id}: {response.get('error', 'unknown error')}"
            )
        if response.get("type") != "ack" or int(response.get("event_id", -1)) != event_id:
            raise RuntimeError(f"unexpected host response for event {event_id}: {response}")

        state = int(response["state"])
        if state not in (BLACK, WHITE):
            raise RuntimeError(f"invalid target state from host: {state}")
        return request_sent_ns, ack_received_ns, state

    def _send(self, message: dict[str, object]) -> None:
        self.writer.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.writer.flush()

    def _receive(self) -> dict[str, object]:
        line = self.reader.readline()
        if not line:
            raise ConnectionError("host closed the control connection")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("host response must be a JSON object")
        return message


def ns_to_ms(delta_ns: int) -> float:
    return delta_ns / 1_000_000.0


def run_event(
    control: ControlClient,
    sampler: ScreenSampler,
    *,
    event_id: int,
    black_threshold: float,
    white_threshold: float,
    debounce_frames: int,
    visual_timeout: float,
) -> BenchmarkRow:
    baseline = sampler.latest_sample()
    if baseline is None:
        raise RuntimeError("screen sampler has no baseline sample")

    request_sent_ns, ack_received_ns, target_state = control.toggle(event_id)
    baseline_state = classify_luminance(
        baseline.mean_luminance,
        black_threshold=black_threshold,
        white_threshold=white_threshold,
    )
    request_to_ack_ms = ns_to_ms(ack_received_ns - request_sent_ns)

    # A toggle is only valid if the ROI was visibly in the opposite state
    # immediately before the request. This prevents a misplaced ROI (for
    # example, a permanently white toolbar) from looking like zero latency.
    if baseline_state != 1 - target_state:
        return BenchmarkRow(
            event_id=event_id,
            status="baseline_mismatch",
            target_state=target_state,
            request_sent_ns=request_sent_ns,
            ack_received_ns=ack_received_ns,
            screen_detected_ns=None,
            request_to_ack_ms=request_to_ack_ms,
            ack_to_screen_ms=None,
            request_to_screen_ms=None,
        )

    screen_detected_ns = sampler.wait_for_state(
        target_state=target_state,
        after_ns=request_sent_ns,
        black_threshold=black_threshold,
        white_threshold=white_threshold,
        debounce_frames=debounce_frames,
        timeout=visual_timeout,
    )

    if screen_detected_ns is None:
        return BenchmarkRow(
            event_id=event_id,
            status="timeout",
            target_state=target_state,
            request_sent_ns=request_sent_ns,
            ack_received_ns=ack_received_ns,
            screen_detected_ns=None,
            request_to_ack_ms=request_to_ack_ms,
            ack_to_screen_ms=None,
            request_to_screen_ms=None,
        )

    return BenchmarkRow(
        event_id=event_id,
        status="ok",
        target_state=target_state,
        request_sent_ns=request_sent_ns,
        ack_received_ns=ack_received_ns,
        screen_detected_ns=screen_detected_ns,
        request_to_ack_ms=request_to_ack_ms,
        ack_to_screen_ms=ns_to_ms(screen_detected_ns - ack_received_ns),
        request_to_screen_ms=ns_to_ms(screen_detected_ns - request_sent_ns),
    )


def write_csv(path: Path, rows: list[BenchmarkRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(BenchmarkRow.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def print_summary(rows: list[BenchmarkRow]) -> None:
    successful = [row for row in rows if row.status == "ok"]
    failed = len(rows) - len(successful)
    print(f"\nSamples: {len(rows)} total, {len(successful)} ok, {failed} failed")

    metrics = (
        ("request_to_ack_ms", [row.request_to_ack_ms for row in successful]),
        (
            "ack_to_screen_ms",
            [row.ack_to_screen_ms for row in successful if row.ack_to_screen_ms is not None],
        ),
        (
            "request_to_screen_ms",
            [
                row.request_to_screen_ms
                for row in successful
                if row.request_to_screen_ms is not None
            ],
        ),
    )
    for name, values in metrics:
        stats = summarize(values)
        if not stats["count"]:
            print(f"{name}: no valid samples")
            continue
        print(
            f"{name}: "
            f"min={stats['min']:.3f} max={stats['max']:.3f} "
            f"mean={stats['mean']:.3f} std={stats['stddev']:.3f} "
            f"p50={stats['p50']:.3f} p90={stats['p90']:.3f} "
            f"p95={stats['p95']:.3f} p99={stats['p99']:.3f}"
        )


def sleep_between(base_ms: float, jitter_ms: float) -> None:
    delay_ms = base_ms + random.uniform(-jitter_ms, jitter_ms)
    time.sleep(max(0.0, delay_ms) / 1000.0)


def state_name(
    mean_luminance: float,
    *,
    black_threshold: float,
    white_threshold: float,
) -> str:
    state = classify_luminance(
        mean_luminance,
        black_threshold=black_threshold,
        white_threshold=white_threshold,
    )
    if state == BLACK:
        return "BLACK"
    if state == WHITE:
        return "WHITE"
    return "MID"


def run_capture_diagnostic(
    control: ControlClient,
    sampler: ScreenSampler,
    *,
    events: int,
    hold_ms: float,
    black_threshold: float,
    white_threshold: float,
) -> None:
    print("\nCapture diagnostic: toggling the host and streaming ROI luminance.")
    for event_id in range(1, events + 1):
        _, _, target_state = control.toggle(event_id)
        target_name = "WHITE" if target_state == WHITE else "BLACK"
        print(f"\nToggle #{event_id}: host target={target_name}")
        steps = 10
        for step in range(steps):
            time.sleep((hold_ms / steps) / 1000.0)
            sample = sampler.latest_sample()
            if sample is None:
                print("  no capture sample")
                continue
            observed = state_name(
                sample.mean_luminance,
                black_threshold=black_threshold,
                white_threshold=white_threshold,
            )
            print(f"  {step + 1:02d}: mean={sample.mean_luminance:6.1f} state={observed}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FastDesk remote visual latency benchmark")
    parser.add_argument("--host", required=True, help="host-agent IP or hostname")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--roi",
        required=True,
        type=parse_roi,
        metavar="LEFT,TOP,WIDTH,HEIGHT",
        help="screen capture rectangle containing the remote test surface",
    )
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=3.0, help="control connection timeout")
    parser.add_argument(
        "--visual-timeout",
        type=float,
        default=2.0,
        help="seconds to wait for each visual transition",
    )
    parser.add_argument("--interval-ms", type=float, default=150.0)
    parser.add_argument("--jitter-ms", type=float, default=40.0)
    parser.add_argument(
        "--capture-backend",
        choices=("dxcam", "mss"),
        default="dxcam",
        help="screen capture backend; dxcam uses Windows Desktop Duplication",
    )
    parser.add_argument(
        "--dxcam-output-idx",
        type=int,
        default=0,
        help="DXcam output/monitor index (default: 0)",
    )
    parser.add_argument(
        "--capture-interval-ms",
        type=float,
        default=0.0,
        help="delay between captures; 0 captures as fast as possible",
    )
    parser.add_argument("--black-threshold", type=float, default=80.0)
    parser.add_argument("--white-threshold", type=float, default=175.0)
    parser.add_argument("--debounce-frames", type=int, default=2)
    parser.add_argument(
        "--diagnose-capture",
        action="store_true",
        help="toggle the host and print live ROI luminance instead of benchmarking",
    )
    parser.add_argument("--diagnose-events", type=int, default=4)
    parser.add_argument("--diagnose-hold-ms", type=float, default=750.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark/results/latest.csv"),
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.samples < 1:
        raise SystemExit("--samples must be >= 1")
    if args.warmup < 0:
        raise SystemExit("--warmup must be >= 0")
    if args.black_threshold >= args.white_threshold:
        raise SystemExit("--black-threshold must be lower than --white-threshold")
    if args.debounce_frames < 1:
        raise SystemExit("--debounce-frames must be >= 1")
    if args.dxcam_output_idx < 0:
        raise SystemExit("--dxcam-output-idx must be >= 0")
    if args.diagnose_events < 1 or args.diagnose_hold_ms <= 0:
        raise SystemExit("diagnostic events/hold values must be positive")
    if args.interval_ms < 0 or args.jitter_ms < 0 or args.capture_interval_ms < 0:
        raise SystemExit("interval/jitter/capture interval values must be >= 0")


def main() -> int:
    args = build_parser().parse_args()
    validate_args(args)

    sampler = ScreenSampler(
        args.roi,
        capture_backend=args.capture_backend,
        capture_interval_ms=args.capture_interval_ms,
        history_seconds=max(5.0, args.visual_timeout * 3),
        dxcam_output_idx=args.dxcam_output_idx,
    )
    sampler.start()

    control: ControlClient | None = None
    rows: list[BenchmarkRow] = []
    try:
        sampler.wait_until_ready(args.timeout)
        print(f"Capture backend: {args.capture_backend}")
        print(f"Initial ROI mean luminance: {sampler.latest_mean():.1f}")
        print(
            "Detection thresholds: "
            f"black <= {args.black_threshold:.1f}, "
            f"white >= {args.white_threshold:.1f}, "
            f"debounce={args.debounce_frames} frame(s)"
        )

        control = ControlClient(args.host, args.port, args.timeout)

        if args.diagnose_capture:
            run_capture_diagnostic(
                control,
                sampler,
                events=args.diagnose_events,
                hold_ms=args.diagnose_hold_ms,
                black_threshold=args.black_threshold,
                white_threshold=args.white_threshold,
            )
            return 0

        next_event_id = 1
        for index in range(args.warmup):
            row = run_event(
                control,
                sampler,
                event_id=next_event_id,
                black_threshold=args.black_threshold,
                white_threshold=args.white_threshold,
                debounce_frames=args.debounce_frames,
                visual_timeout=args.visual_timeout,
            )
            if row.status != "ok":
                raise RuntimeError(
                    f"warmup event {next_event_id} failed with status={row.status}; "
                    "check ROI, thresholds, and whether the remote target is visible"
                )
            print(f"Warmup {index + 1}/{args.warmup}: {row.request_to_screen_ms:.3f} ms")
            next_event_id += 1
            sleep_between(args.interval_ms, args.jitter_ms)

        for index in range(args.samples):
            row = run_event(
                control,
                sampler,
                event_id=next_event_id,
                black_threshold=args.black_threshold,
                white_threshold=args.white_threshold,
                debounce_frames=args.debounce_frames,
                visual_timeout=args.visual_timeout,
            )
            rows.append(row)
            if row.status == "ok":
                print(
                    f"Sample {index + 1}/{args.samples}: "
                    f"ack={row.request_to_ack_ms:.3f} ms "
                    f"visual={row.ack_to_screen_ms:.3f} ms "
                    f"total={row.request_to_screen_ms:.3f} ms"
                )
            else:
                print(
                    f"Sample {index + 1}/{args.samples}: {row.status.upper()} "
                    f"(event {row.event_id}); check ROI/thresholds if this persists",
                    file=sys.stderr,
                )
            next_event_id += 1
            sleep_between(args.interval_ms, args.jitter_ms)
    finally:
        if control is not None:
            control.close()
        sampler.stop()
        if rows:
            write_csv(args.output, rows)
            print(f"\nCSV: {args.output}")

    if not rows:
        return 2

    print_summary(rows)
    failures = sum(row.status != "ok" for row in rows)
    if failures:
        print(
            f"ERROR: {failures} measured event(s) had no detectable visual transition.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
