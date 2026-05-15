from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.crawler import crawl_sources
from glowbal_ingestion.crawler import is_blocked_response


class CrawlerTests(unittest.TestCase):
    def test_crawler_extracts_text_from_local_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "page.html"
            html_path.write_text(
                "<html><head><title>Admissions</title><script>hidden()</script></head>"
                "<body><h1>International admissions</h1><p>IELTS 7.0 required.</p></body></html>",
                encoding="utf-8",
            )
            out_dir = Path(tmp) / "out"

            sources, evidence = crawl_sources(
                [
                    {
                        "university_id": "demo",
                        "university_name": "Demo University",
                        "country": "Japan",
                        "source_type": "english_requirements",
                        "url": html_path.as_uri(),
                        "priority": "1",
                        "language_code": "en",
                        "crawl_method": "static",
                        "notes": "",
                    }
                ],
                out_dir,
            )

        self.assertEqual(sources[0]["status"], "fetched")
        self.assertEqual(evidence[0]["status"], "ok")
        self.assertEqual(evidence[0]["title"], "Admissions")
        self.assertIn("IELTS 7.0 required", evidence[0]["extracted_text"])
        self.assertNotIn("hidden", evidence[0]["extracted_text"])

    def test_blocked_response_detection(self) -> None:
        self.assertTrue(is_blocked_response("Request unsuccessful. Incapsula incident ID: 123"))
        self.assertFalse(is_blocked_response("International admissions and English language requirements."))

    def test_playwright_sources_skip_when_package_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _sources, evidence = crawl_sources(
                [
                    {
                        "university_id": "demo",
                        "university_name": "Demo University",
                        "country": "Japan",
                        "source_type": "official_home",
                        "url": "https://example.edu",
                        "priority": "1",
                        "language_code": "en",
                        "crawl_method": "playwright",
                        "notes": "",
                    }
                ],
                Path(tmp),
            )
        if evidence[0]["status"] == "playwright_required":
            self.assertIn("playwright package is not installed", evidence[0]["error"])


if __name__ == "__main__":
    unittest.main()
