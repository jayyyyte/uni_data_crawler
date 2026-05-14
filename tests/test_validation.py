from __future__ import annotations

import unittest

from glowbal_ingestion.validation import validate_seed_rows, validate_source_rows


class ValidationTests(unittest.TestCase):
    def test_source_validation_catches_duplicate_and_bad_type(self) -> None:
        seed = [
            {
                "university_id": "mit",
                "name": "MIT",
                "country": "United States",
                "city": "Cambridge",
                "website_url": "https://web.mit.edu",
                "type": "private",
            }
        ]
        sources = [
            {
                "university_id": "mit",
                "university_name": "MIT",
                "country": "United States",
                "source_type": "tuition_fees",
                "url": "https://example.edu/fees",
                "crawl_method": "static",
            },
            {
                "university_id": "mit",
                "university_name": "MIT",
                "country": "United States",
                "source_type": "bad_source",
                "url": "https://example.edu/fees",
                "crawl_method": "static",
            },
        ]

        errors = validate_seed_rows(seed) + validate_source_rows(sources, seed)

        self.assertTrue(any("unsupported source_type" in error for error in errors))
        self.assertTrue(any("duplicate URL" in error for error in errors))

    def test_seed_validation_rejects_bad_url(self) -> None:
        errors = validate_seed_rows(
            [
                {
                    "university_id": "x",
                    "name": "X",
                    "country": "Nowhere",
                    "city": "City",
                    "website_url": "not-a-url",
                    "type": "unknown",
                }
            ]
        )
        self.assertTrue(any("invalid website_url" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

