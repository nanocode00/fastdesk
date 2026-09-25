from __future__ import annotations

import unittest

import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_DIR))

from core import BLACK, WHITE, LuminanceSample, classify_luminance, find_stable_transition, parse_roi, percentile, summarize


class CoreTests(unittest.TestCase):
    def test_classify_luminance(self) -> None:
        self.assertEqual(
            classify_luminance(10, black_threshold=80, white_threshold=175),
            BLACK,
        )
        self.assertEqual(
            classify_luminance(240, black_threshold=80, white_threshold=175),
            WHITE,
        )
        self.assertIsNone(
            classify_luminance(120, black_threshold=80, white_threshold=175)
        )

    def test_stable_transition_requires_debounce(self) -> None:
        samples = [
            LuminanceSample(100, 10),
            LuminanceSample(200, 240),
            LuminanceSample(300, 20),
            LuminanceSample(400, 230),
            LuminanceSample(500, 235),
        ]
        detected = find_stable_transition(
            samples,
            target_state=WHITE,
            after_ns=150,
            black_threshold=80,
            white_threshold=175,
            debounce_frames=2,
        )
        self.assertEqual(detected, 400)

    def test_stable_transition_respects_after_timestamp(self) -> None:
        samples = [
            LuminanceSample(100, 240),
            LuminanceSample(200, 240),
            LuminanceSample(300, 10),
            LuminanceSample(400, 240),
            LuminanceSample(500, 240),
        ]
        detected = find_stable_transition(
            samples,
            target_state=WHITE,
            after_ns=250,
            black_threshold=80,
            white_threshold=175,
            debounce_frames=2,
        )
        self.assertEqual(detected, 400)

    def test_percentile_and_summary(self) -> None:
        self.assertEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        stats = summarize([1, 2, 3, 4, 5])
        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["min"], 1)
        self.assertEqual(stats["max"], 5)
        self.assertEqual(stats["p50"], 3)

    def test_parse_roi(self) -> None:
        self.assertEqual(parse_roi("10,20,800,600"), (10, 20, 800, 600))
        with self.assertRaises(ValueError):
            parse_roi("10,20,0,600")


if __name__ == "__main__":
    unittest.main()
