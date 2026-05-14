from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.discovery import suggest_sources


class DiscoveryTests(unittest.TestCase):
    def test_suggest_sources_classifies_homepage_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "index.html"
            html_path.write_text(
                """
                <html><body>
                  <a href="https://demo.edu/admissions/international">International admissions</a>
                  <a href="https://demo.edu/tuition-fees">Tuition and fees</a>
                  <a href="https://other.edu/tuition">Wrong domain</a>
                </body></html>
                """,
                encoding="utf-8",
            )
            out = Path(tmp) / "suggestions.csv"
            suggestions = suggest_sources(
                [
                    {
                        "university_id": "demo",
                        "university_name": "Demo University",
                        "source_type": "official_home",
                        "url": html_path.as_uri(),
                    }
                ],
                out,
            )

        source_types = {row["candidate_source_type"] for row in suggestions}
        self.assertIn("international_admissions", source_types)
        self.assertIn("tuition_fees", source_types)


if __name__ == "__main__":
    unittest.main()
