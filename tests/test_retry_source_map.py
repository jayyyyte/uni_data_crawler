from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.source_map_tools import build_retry_source_map


class RetrySourceMapTests(unittest.TestCase):
    def test_build_retry_source_map_filters_status_and_source_type(self) -> None:
        sources = [
            {
                "source_id": "a",
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://demo.edu/fees",
                "status": "failed",
            },
            {
                "source_id": "b",
                "university_id": "demo",
                "source_type": "career",
                "url": "https://demo.edu/career",
                "status": "failed",
            },
            {
                "source_id": "c",
                "university_id": "demo",
                "source_type": "official_home",
                "url": "https://demo.edu",
                "status": "fetched",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            rows = build_retry_source_map(sources, Path(tmp) / "retry.csv", source_types={"tuition_fees"})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "a")
        self.assertEqual(rows[0]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
