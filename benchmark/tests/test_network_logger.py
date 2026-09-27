from __future__ import annotations

import sys
import unittest
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCHMARK_DIR))

from network_logger import (
    ProbeResult,
    build_ping_command,
    parse_ping_rtt_ms,
    rolling_loss_percent,
    summarize_results,
)


class NetworkLoggerTests(unittest.TestCase):
    def test_parse_ping_rtt_english(self) -> None:
        output = "Reply from 100.64.0.1: bytes=32 time=18ms TTL=128"
        self.assertEqual(parse_ping_rtt_ms(output), 18.0)

    def test_parse_ping_rtt_korean(self) -> None:
        output = "100.64.0.1의 응답: 바이트=32 시간=27ms TTL=128"
        self.assertEqual(parse_ping_rtt_ms(output), 27.0)

    def test_parse_ping_rtt_sub_millisecond(self) -> None:
        output = "Reply from 127.0.0.1: bytes=32 time<1ms TTL=128"
        self.assertEqual(parse_ping_rtt_ms(output), 0.5)

    def test_parse_ping_rtt_linux_decimal(self) -> None:
        output = "64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=13.4 ms"
        self.assertEqual(parse_ping_rtt_ms(output), 13.4)

    def test_build_windows_ping_command(self) -> None:
        self.assertEqual(
            build_ping_command(
                "100.64.0.1",
                timeout_ms=200,
                system_name="Windows",
            ),
            ["ping", "-n", "1", "-w", "200", "100.64.0.1"],
        )

    def test_rolling_loss_percent(self) -> None:
        self.assertEqual(
            rolling_loss_percent([False, True, False, True]),
            50.0,
        )

    def test_summarize_results(self) -> None:
        rows = [
            ProbeResult("ok", True, 10.0, 0, 12.0),
            ProbeResult("ok", True, 14.0, 0, 16.0),
            ProbeResult("timeout", False, None, 1, 200.0),
            ProbeResult("ok", True, 18.0, 0, 20.0),
        ]
        summary = summarize_results(rows)

        self.assertEqual(summary["samples"], 4)
        self.assertEqual(summary["successes"], 3)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["loss_pct"], 25.0)
        self.assertEqual(summary["rtt_ms"]["p50"], 14.0)
        self.assertEqual(summary["rtt_abs_delta_ms"]["mean"], 4.0)


if __name__ == "__main__":
    unittest.main()
