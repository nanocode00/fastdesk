from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence


BLACK = 0
WHITE = 1


@dataclass(frozen=True)
class LuminanceSample:
    timestamp_ns: int
    mean_luminance: float


def classify_luminance(
    mean_luminance: float,
    *,
    black_threshold: float,
    white_threshold: float,
) -> int | None:
    if black_threshold >= white_threshold:
        raise ValueError("black_threshold must be lower than white_threshold")
    if mean_luminance <= black_threshold:
        return BLACK
    if mean_luminance >= white_threshold:
        return WHITE
    return None


def find_stable_transition(
    samples: Sequence[LuminanceSample],
    *,
    target_state: int,
    after_ns: int,
    black_threshold: float,
    white_threshold: float,
    debounce_frames: int,
) -> int | None:
    if target_state not in (BLACK, WHITE):
        raise ValueError("target_state must be 0 (black) or 1 (white)")
    if debounce_frames < 1:
        raise ValueError("debounce_frames must be >= 1")

    run_start_ns: int | None = None
    run_length = 0

    for sample in samples:
        if sample.timestamp_ns < after_ns:
            continue
        state = classify_luminance(
            sample.mean_luminance,
            black_threshold=black_threshold,
            white_threshold=white_threshold,
        )
        if state == target_state:
            if run_length == 0:
                run_start_ns = sample.timestamp_ns
            run_length += 1
            if run_length >= debounce_frames:
                return run_start_ns
        else:
            run_start_ns = None
            run_length = 0

    return None


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be between 0 and 100")

    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * (q / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(values: Iterable[float]) -> dict[str, float | int]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {"count": 0}

    return {
        "count": len(numbers),
        "min": min(numbers),
        "max": max(numbers),
        "mean": statistics.fmean(numbers),
        "stddev": statistics.pstdev(numbers),
        "p50": percentile(numbers, 50),
        "p90": percentile(numbers, 90),
        "p95": percentile(numbers, 95),
        "p99": percentile(numbers, 99),
    }


def parse_roi(value: str) -> tuple[int, int, int, int]:
    try:
        left, top, width, height = (int(part.strip()) for part in value.split(","))
    except (TypeError, ValueError) as exc:
        raise ValueError("ROI must be LEFT,TOP,WIDTH,HEIGHT") from exc

    if width <= 0 or height <= 0:
        raise ValueError("ROI width and height must be positive")
    return left, top, width, height
