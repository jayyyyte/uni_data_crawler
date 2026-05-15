from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.extractors import extract_facts


class ExtractorTests(unittest.TestCase):
    def test_extractors_emit_evidence_backed_facts(self) -> None:
        sources = [
            {
                "source_id": "src_1",
                "university_id": "demo",
                "source_type": "tuition_fees",
                "url": "https://example.edu/fees",
            },
            {
                "source_id": "src_2",
                "university_id": "demo",
                "source_type": "english_requirements",
                "url": "https://example.edu/english",
            },
            {
                "source_id": "src_3",
                "university_id": "demo",
                "source_type": "program_catalog",
                "url": "https://example.edu/programs",
            },
        ]
        evidence = [
            {
                "evidence_id": "ev_1",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://example.edu/fees",
                "status": "ok",
                "extracted_text": "International tuition is USD 45000 to USD 52000 per year for Engineering and Computer Science.",
            },
            {
                "evidence_id": "ev_2",
                "source_id": "src_2",
                "university_id": "demo",
                "url": "https://example.edu/english",
                "status": "ok",
                "extracted_text": "English requirements include IELTS 7.0 or TOEFL 100.",
            },
            {
                "evidence_id": "ev_3",
                "source_id": "src_3",
                "university_id": "demo",
                "url": "https://example.edu/programs",
                "status": "ok",
                "extracted_text": "Bachelor programs include Engineering and Computer Science.",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            facts, _programs = extract_facts(sources, evidence, Path(tmp))

        self.assertTrue(facts)
        self.assertTrue(all(fact["evidence_id"] for fact in facts))
        self.assertTrue(all(fact["source_url"] for fact in facts))
        self.assertTrue(any(fact["fact_type"] == "tuition" for fact in facts))
        self.assertTrue(any(fact["fact_key"] == "IELTS" for fact in facts))
        self.assertTrue(any(fact["value_text"] == "computer_science" for fact in facts))

    def test_english_summary_fallback_without_numeric_score(self) -> None:
        sources = [
            {
                "source_id": "src_1",
                "university_id": "demo",
                "source_type": "english_requirements",
                "url": "https://example.edu/english",
            },
        ]
        evidence = [
            {
                "evidence_id": "ev_1",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://example.edu/english",
                "status": "ok",
                "extracted_text": "A strong knowledge of English is essential for successful study. English language proficiency examinations such as TOEFL and IELTS may be submitted for review.",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            facts, _programs = extract_facts(sources, evidence, Path(tmp))

        self.assertTrue(any(fact["fact_type"] == "english_requirement" and fact["fact_key"] == "summary" for fact in facts))


if __name__ == "__main__":
    unittest.main()
