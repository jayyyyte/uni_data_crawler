from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.source_map_tools import apply_source_repairs


class ApplySourceRepairsTests(unittest.TestCase):
    def test_apply_source_repairs_updates_url_and_resets_status(self) -> None:
        seed = [{"university_id": "demo", "name": "Demo University", "country": "United States"}]
        base = [
            {
                "source_id": "src_demo",
                "university_id": "demo",
                "university_name": "Old Name",
                "country": "USA",
                "source_type": "tuition_fees",
                "url": "https://old.example/fees",
                "priority": "2",
                "language_code": "en",
                "crawl_method": "static",
                "status": "failed",
                "last_crawled_at": "yesterday",
                "notes": "old",
            }
        ]
        repairs = [
            {
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://new.example/fees",
                "crawl_method": "playwright",
                "notes": "fixed",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sources.csv"
            stats = apply_source_repairs(seed, base, repairs, out)
            rows = read_csv(out)

        self.assertEqual(stats["updated_rows"], 1)
        self.assertEqual(rows[0]["url"], "https://new.example/fees")
        self.assertEqual(rows[0]["crawl_method"], "playwright")
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["university_name"], "Demo University")

    def test_apply_source_repairs_updates_only_one_row_per_key(self) -> None:
        seed = [{"university_id": "demo", "name": "Demo University", "country": "United States"}]
        base = [
            {
                "source_id": "a",
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://old.example/a",
                "priority": "2",
                "crawl_method": "static",
                "status": "failed",
            },
            {
                "source_id": "b",
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://old.example/b",
                "priority": "2",
                "crawl_method": "static",
                "status": "failed",
            },
        ]
        repairs = [
            {
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://new.example/fees",
                "crawl_method": "playwright",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sources.csv"
            stats = apply_source_repairs(seed, base, repairs, out)
            rows = read_csv(out)

        self.assertEqual(stats["updated_rows"], 1)
        self.assertEqual(sum(row["url"] == "https://new.example/fees" for row in rows), 1)


if __name__ == "__main__":
    unittest.main()
