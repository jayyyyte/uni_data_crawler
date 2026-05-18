from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.source_search import promote_search_sources, search_source_candidates


class SourceSearchTests(unittest.TestCase):
    def test_search_source_candidates_writes_reviewable_rows(self) -> None:
        seed = [{"university_id": "demo", "name": "Demo University", "country": "US", "website_url": "https://demo.edu"}]
        existing = [{"university_id": "demo", "source_type": "official_home", "url": "https://demo.edu"}]

        with tempfile.TemporaryDirectory() as tmp, patch("glowbal_ingestion.source_search.serper_search") as serper:
            serper.return_value = [{"link": "https://demo.edu/admissions", "title": "Admissions", "snippet": "Apply to Demo"}]
            out = Path(tmp) / "candidates.csv"
            rows = search_source_candidates(seed, existing, out, {"undergraduate_admissions"}, api_key="key")

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["review_status"], "needs_review")
            self.assertEqual(read_csv(out)[0]["candidate_url"], "https://demo.edu/admissions")

    def test_promote_search_sources_only_accepts_approved_rows(self) -> None:
        seed = [{"university_id": "demo", "name": "Demo University", "country": "US"}]
        base = [{"source_id": "src_home", "university_id": "demo", "source_type": "official_home", "url": "https://demo.edu"}]
        candidates = [
            {
                "university_id": "demo",
                "source_type": "tuition_fees",
                "candidate_url": "https://demo.edu/fees",
                "review_status": "approved",
                "crawl_method": "playwright",
            },
            {
                "university_id": "demo",
                "source_type": "english_requirements",
                "candidate_url": "https://demo.edu/english",
                "review_status": "needs_review",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            rows = promote_search_sources(seed, base, candidates, Path(tmp) / "sources.csv")

        self.assertEqual(len(rows), 2)
        promoted = [row for row in rows if row.get("source_type") == "tuition_fees"][0]
        self.assertEqual(promoted["crawl_method"], "playwright")
        self.assertFalse(any(row.get("source_type") == "english_requirements" for row in rows))


if __name__ == "__main__":
    unittest.main()
