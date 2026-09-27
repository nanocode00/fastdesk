from __future__ import annotations

import argparse
import csv
import math
import platform
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from core import summarize


_RTT_RE = re.compile(r"(?:=|<)\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


@dataclass(frozen=True)
class ProbeResult:
    status: str
    success: bool
    rtt_ms: float | None
    returncode: int | None
    probe_elapsed_ms: float


def parse_ping_rtt_ms(output: str) -> float | None:
    """Extract the first RTT value from localized ping output.

    Matching the numeric value before ms avoids depending on words such as
    time or Korean-localized labels. Values reported as less than 1 ms are
    represented as 0.5 ms so they remain distinguishable from a missing RTT.
    """

    match = _RTT_RE.search(output)
    if match is None:
        return None

    token = match.group(1).replace(",", ".")
    value = float(token)

    prefix = output[max(0, match.start() - 2) : match.start() + 1]
    if "<" in prefix and value == 1.0:
        return 0.5
    return value


def build_ping_command(
    target: str,
    *,
    timeout_ms: int,
    system_name: str | None = None,
) -> list[str]:
    system_name = system_name or platform.system()

    if system_name == "Windows":
        return ["ping", "-n", "1", "-w", str(timeout_ms), target]
    if system_name == "Darwin":
        return ["ping", "-n", "-c", "1", "-W", str(timeout_ms), target]

    timeout_seconds = max(1, math.ceil(timeout_ms / 1000))
    return ["ping", "-n", "-c", "1", "-W", str(timeout_seconds), target]


def run_ping(
    target: str,
    *,
    timeout_ms: int,
    system_name: str | None = None,
) -> ProbeResult:
    command = build_ping_command(
        target,
        timeout_ms=timeout_ms,
        system_name=system_name,
    )
    started_ns = time.perf_counter_ns()

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(1.0, timeout_ms / 1000.0 + 1.0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
        return ProbeResult(
            status="timeout",
            success=False,
            rtt_ms=None,
            returncode=None,
            probe_elapsed_ms=elapsed_ms,
        )
    except OSError:
        elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
        return ProbeResult(
            status="error",
            success=False,
            rtt_ms=None,
            returncode=None,
            probe_elapsed_ms=elapsed_ms,
        )

    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
    combined_output = f"{completed.stdout}\\n{completed.stderr}"
    rtt_ms = parse_ping_rtt_ms(combined_output)

    if completed.returncode == 0:
        status = "ok" if rtt_ms is not None else "parse_error"
        return ProbeResult(
            status=status,
            success=True,
            rtt_ms=rtt_ms,
            returncode=completed.returncode,
            probe_elapsed_ms=elapsed_ms,
        )

    lowered = combined_output.lower()
    if "timed out" in lowered or "timeout" in lowered:
        status = "timeout"
    else:
        status = "unreachable"

    return ProbeResult(
        status=status,
        success=False,
        rtt_ms=None,
        returncode=completed.returncode,
        probe_elapsed_ms=elapsed_ms,
    )


def rolling_loss_percent(losses: Sequence[bool]) -> float:
    if not losses:
        return 0.0
    return 100.0 * sum(1 for lost in losses if lost) / len(losses)


def summarize_results(results: Iterable[ProbeResult]) -> dict[str, object]:
    rows = list(results)
    rtts = [row.rtt_ms for row in rows if row.rtt_ms is not None]
    failed = sum(1 for row in rows if not row.success)
    parse_errors = sum(1 for row in rows if row.status == "parse_error")

    rtt_deltas = [
        abs(right - left)
        for left, right in zip(rtts, rtts[1:])
    ]

    return {
        "samples": len(rows),
        "successes": len(rows) - failed,
        "failed": failed,
        "loss_pct": 100.0 * failed / len(rows) if rows else 0.0,
        "parse_errors": parse_errors,
        "rtt_ms": summarize(rtts),
        "rtt_abs_delta_ms": summarize(rtt_deltas),
    }


def default_output_path() -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return Path("benchmark") / "results" / f"network-{stamp}.csv"


def print_summary(summary: dict[str, object]) -> None:
    print("\\nNetwork logger summary")
    print(
        f"  samples={summary['samples']} "
        f"success={summary['successes']} "
        f"failed={summary['failed']} "
        f"loss={float(summary['loss_pct']):.2f}% "
        f"parse_errors={summary['parse_errors']}"
    )

    rtt = summary["rtt_ms"]
    if isinstance(rtt, dict) and rtt.get("count", 0):
        print(
            "  RTT ms: "
            f"p50={float(rtt['p50']):.2f} "
            f"p95={float(rtt['p95']):.2f} "
            f"p99={float(rtt['p99']):.2f} "
            f"min={float(rtt['min']):.2f} "
            f"max={float(rtt['max']):.2f}"
        )

    jitter = summary["rtt_abs_delta_ms"]
    if isinstance(jitter, dict) and jitter.get("count", 0):
        print(
            "  |RTT delta| ms: "
            f"mean={float(jitter['mean']):.2f} "
            f"p95={float(jitter['p95']):.2f} "
            f"max={float(jitter['max']):.2f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Log ICMP RTT/loss at a fixed cadence so RustDesk quality-monitor "
            "spikes can be correlated with network conditions."
        )
    )
    parser.add_argument("target", help="IP address or host name to probe")
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=250,
        help="probe cadence in milliseconds (default: 250)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=200,
        help="per-probe ping timeout in milliseconds (default: 200)",
    )
    parser.add_argument(
        "--rolling-window",
        type=int,
        default=20,
        help="samples used for rolling loss percentage (default: 20)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="optional run duration in seconds; otherwise stop with Ctrl+C",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path (default: benchmark/results/network-TIMESTAMP.csv)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress one-line live output for every probe",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.interval_ms < 50:
        raise SystemExit("--interval-ms must be >= 50")
    if args.timeout_ms < 1:
        raise SystemExit("--timeout-ms must be >= 1")
    if args.rolling_window < 1:
        raise SystemExit("--rolling-window must be >= 1")
    if args.duration is not None and args.duration <= 0:
        raise SystemExit("--duration must be > 0")


def main() -> int:
    args = parse_args()
    validate_args(args)

    output = args.output or default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    interval_ns = args.interval_ms * 1_000_000
    rolling_losses: deque[bool] = deque(maxlen=args.rolling_window)
    results: list[ProbeResult] = []
    previous_rtt_ms: float | None = None

    started_wall = datetime.now().astimezone()
    started_ns = time.perf_counter_ns()
    next_probe_ns = started_ns

    print(f"Target: {args.target}")
    print(
        f"Interval: {args.interval_ms} ms | "
        f"timeout: {args.timeout_ms} ms | "
        f"rolling window: {args.rolling_window} samples"
    )
    print(f"Started: {started_wall.isoformat(timespec='milliseconds')}")
    print(f"CSV: {output}")
    print("Press Ctrl+C to stop.\\n")

    fieldnames = [
        "seq",
        "timestamp_iso",
        "unix_ms",
        "monotonic_ns",
        "target",
        "status",
        "rtt_ms",
        "rtt_delta_ms",
        "probe_elapsed_ms",
        "scheduler_lag_ms",
        "rolling_loss_pct",
        "returncode",
        "skipped_intervals",
    ]

    try:
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

            seq = 0
            while True:
                now_ns = time.perf_counter_ns()
                if args.duration is not None:
                    elapsed_s = (now_ns - started_ns) / 1_000_000_000.0
                    if elapsed_s >= args.duration:
                        break

                if now_ns < next_probe_ns:
                    time.sleep((next_probe_ns - now_ns) / 1_000_000_000.0)

                probe_started_ns = time.perf_counter_ns()
                scheduler_lag_ms = max(
                    0.0,
                    (probe_started_ns - next_probe_ns) / 1_000_000.0,
                )
                wall = datetime.now().astimezone()
                unix_ms = int(time.time() * 1000)

                result = run_ping(
                    args.target,
                    timeout_ms=args.timeout_ms,
                )
                results.append(result)
                rolling_losses.append(not result.success)
                seq += 1

                rtt_delta_ms: float | None = None
                if result.rtt_ms is not None:
                    if previous_rtt_ms is not None:
                        rtt_delta_ms = abs(result.rtt_ms - previous_rtt_ms)
                    previous_rtt_ms = result.rtt_ms

                after_probe_ns = time.perf_counter_ns()
                next_probe_ns += interval_ns
                skipped_intervals = 0
                while next_probe_ns <= after_probe_ns:
                    next_probe_ns += interval_ns
                    skipped_intervals += 1

                writer.writerow(
                    {
                        "seq": seq,
                        "timestamp_iso": wall.isoformat(timespec="milliseconds"),
                        "unix_ms": unix_ms,
                        "monotonic_ns": probe_started_ns,
                        "target": args.target,
                        "status": result.status,
                        "rtt_ms": (
                            f"{result.rtt_ms:.3f}"
                            if result.rtt_ms is not None
                            else ""
                        ),
                        "rtt_delta_ms": (
                            f"{rtt_delta_ms:.3f}"
                            if rtt_delta_ms is not None
                            else ""
                        ),
                        "probe_elapsed_ms": f"{result.probe_elapsed_ms:.3f}",
                        "scheduler_lag_ms": f"{scheduler_lag_ms:.3f}",
                        "rolling_loss_pct": (
                            f"{rolling_loss_percent(list(rolling_losses)):.2f}"
                        ),
                        "returncode": (
                            result.returncode
                            if result.returncode is not None
                            else ""
                        ),
                        "skipped_intervals": skipped_intervals,
                    }
                )
                handle.flush()

                if not args.quiet:
                    rtt_text = (
                        f"{result.rtt_ms:7.2f} ms"
                        if result.rtt_ms is not None
                        else "      --"
                    )
                    print(
                        f"{wall.strftime('%H:%M:%S.%f')[:-3]} "
                        f"#{seq:05d} {result.status:11s} "
                        f"RTT={rtt_text} "
                        f"loss[{len(rolling_losses):02d}]="
                        f"{rolling_loss_percent(list(rolling_losses)):5.1f}%"
                    )
    except KeyboardInterrupt:
        print("\\nStopped by user.")

    print_summary(summarize_results(results))
    print(f"CSV saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
