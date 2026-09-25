from __future__ import annotations

import ast
import unittest
from pathlib import Path


class SourceSyntaxTests(unittest.TestCase):
    def test_benchmark_python_sources_parse(self) -> None:
        benchmark_dir = Path(__file__).resolve().parents[1]
        for path in sorted(benchmark_dir.glob("*.py")):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
