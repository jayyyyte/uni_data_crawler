from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.discovery import build_candidate_source_map


class CandidateSourceMapTests(unittest.TestCase):
    def test_build_candidate_source_map_keeps_homepage_and_adds_top_candidate(self) -> None:
        sources = [
            {
                "source_id": "src_1",
                "university_id": "demo",
                "university_name": "Demo University",
                "country": "United States",
                "source_type": "official_home",
                "url": "https://demo.edu",
                "priority": "1",
                "language_code": "en",
                "crawl_method": "static",
                "notes": "",
            }
        ]
        suggestions = [
            {
                "university_id": "demo",
                "university_name": "Demo University",
                "candidate_source_type": "tuition_fees",
                "url": "https://demo.edu/fees-long-page",
                "confidence_score": "0.55",
                "reason": "matched keyword 'fees'",
            },
            {
                "university_id": "demo",
                "university_name": "Demo University",
                "candidate_source_type": "tuition_fees",
                "url": "https://demo.edu/tuition",
                "confidence_score": "0.75",
                "reason": "matched keyword 'tuition'",
            },
            {
                "university_id": "demo",
                "university_name": "Demo University",
                "candidate_source_type": "scholarships",
                "url": "https://demo.edu/tuition",
                "confidence_score": "0.75",
                "reason": "matched keyword 'funding'",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            rows = build_candidate_source_map(sources, suggestions, Path(tmp) / "candidate.csv")

        self.assertEqual(len(rows), 2)
        self.assertTrue(any(row["source_type"] == "official_home" for row in rows))
        self.assertTrue(any(row["url"] == "https://demo.edu/tuition" for row in rows))
        self.assertFalse(any(row["url"] == "https://demo.edu/fees-long-page" for row in rows))
        self.assertEqual(sum(row["url"] == "https://demo.edu/tuition" for row in rows), 1)


if __name__ == "__main__":
    unittest.main()
