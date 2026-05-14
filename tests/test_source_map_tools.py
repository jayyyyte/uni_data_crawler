from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.source_map_tools import normalize_source_map


class SourceMapToolsTests(unittest.TestCase):
    def test_normalize_source_map_maps_aliases_and_removes_bad_rows(self) -> None:
        seed = [
            {
                "university_id": "amsterdam",
                "name": "University of Amsterdam",
                "country": "Netherlands",
            }
        ]
        rows = [
            {
                "source_id": "src_uva_01",
                "university_id": "uva_nl",
                "university_name": "University of Amsterdam",
                "country": "Netherlands",
                "source_type": "tuition_fees",
                "url": "https://www.uva.nl/fees",
                "priority": "2",
                "language_code": "en",
                "crawl_method": "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": "",
            },
            {
                "source_id": "",
                "university_id": "",
                "university_name": "",
                "country": "",
                "source_type": "",
                "url": "",
                "priority": "",
                "language_code": "",
                "crawl_method": "",
                "status": "",
                "last_crawled_at": "",
                "notes": "",
            },
            {
                "source_id": "bad",
                "university_id": "amsterdam",
                "university_name": "University of Amsterdam",
                "country": "Netherlands",
                "source_type": "tuition_fees",
                "url": "not a url",
                "priority": "2",
                "language_code": "en",
                "crawl_method": "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": "",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "sources.csv"
            stats = normalize_source_map(seed, rows, out)
            normalized = read_csv(out)

        self.assertEqual(stats["mapped_university_ids"], 1)
        self.assertEqual(stats["removed_blank_rows"], 1)
        self.assertEqual(stats["removed_invalid_url_rows"], 1)
        self.assertEqual(normalized[0]["university_id"], "amsterdam")
        self.assertEqual(normalized[0]["country"], "Netherlands")


if __name__ == "__main__":
    unittest.main()
