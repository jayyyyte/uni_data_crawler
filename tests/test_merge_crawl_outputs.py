from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.source_map_tools import merge_crawl_outputs


class MergeCrawlOutputsTests(unittest.TestCase):
    def test_merge_replaces_successful_retry_and_latest_failed_attempts(self) -> None:
        base_sources = [
            {"source_id": "a", "status": "failed", "url": "https://demo.edu/a"},
            {"source_id": "b", "status": "failed", "url": "https://demo.edu/b"},
        ]
        base_evidence = [
            {"evidence_id": "base-a", "source_id": "a", "status": "failed", "url": "https://demo.edu/a"},
            {"evidence_id": "base-b", "source_id": "b", "status": "failed", "url": "https://demo.edu/b"},
        ]
        retry_sources = [
            {"source_id": "a", "status": "fetched", "url": "https://demo.edu/a"},
            {"source_id": "b", "status": "failed", "url": "https://demo.edu/b"},
        ]
        retry_evidence = [
            {"evidence_id": "retry-a", "source_id": "a", "status": "ok", "url": "https://demo.edu/a"},
            {"evidence_id": "retry-b", "source_id": "b", "status": "failed", "url": "https://demo.edu/b"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            stats = merge_crawl_outputs(base_sources, base_evidence, retry_sources, retry_evidence, Path(tmp))
            merged_sources = read_csv(Path(tmp) / "sources.csv")
            merged_evidence = read_csv(Path(tmp) / "evidence.csv")

        self.assertEqual(stats["sources_replaced"], 2)
        self.assertEqual(stats["evidence_replaced"], 2)
        self.assertEqual(merged_sources[0]["status"], "fetched")
        self.assertEqual(merged_sources[1]["status"], "failed")
        self.assertEqual(merged_evidence[0]["evidence_id"], "retry-a")
        self.assertEqual(merged_evidence[1]["evidence_id"], "retry-b")


if __name__ == "__main__":
    unittest.main()
