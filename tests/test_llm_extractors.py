from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glowbal_ingestion.csv_io import read_csv, write_csv
from glowbal_ingestion.llm_extractors import extract_facts_with_llm, llm_response_to_facts


class LlmExtractorTests(unittest.TestCase):
    def test_llm_response_to_facts_requires_supporting_text(self) -> None:
        evidence = {
            "evidence_id": "ev_1",
            "university_id": "demo",
            "url": "https://demo.edu/fees",
            "extracted_text": "International tuition is USD 45000 per year. IELTS 7.0 is required.",
        }
        source = {"source_type": "tuition_fees"}
        response = {
            "tuition_facts": [
                {"amount_min": 45000, "amount_max": 45000, "currency": "USD", "supporting_text": "International tuition is USD 45000 per year.", "confidence_score": 0.9},
                {"amount_min": 99999, "amount_max": 99999, "currency": "USD", "supporting_text": "This quote is not present.", "confidence_score": 0.9},
            ],
            "deadline_facts": [],
            "english_requirement_facts": [
                {"test": "IELTS", "overall_score": 7.0, "supporting_text": "IELTS 7.0 is required.", "confidence_score": 0.8}
            ],
            "cert_requirement_facts": [],
            "application_facts": [],
            "scholarship_facts": [],
            "program_facts": [],
        }

        facts = llm_response_to_facts(evidence, source, response)

        self.assertEqual(len([fact for fact in facts if fact["fact_type"] == "tuition"]), 1)
        self.assertTrue(all(fact["supporting_text"] for fact in facts))
        self.assertTrue(all(fact["fact_origin"] == "llm_extracted_from_source" for fact in facts))

    def test_extract_facts_with_llm_skips_non_usable_evidence_and_merges(self) -> None:
        sources = [{"source_id": "src_1", "university_id": "demo", "source_type": "english_requirements", "url": "https://demo.edu/english"}]
        evidence = [
            {
                "evidence_id": "ev_1",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://demo.edu/english",
                "status": "ok",
                "content_quality_status": "usable",
                "extracted_text": "IELTS 7.0 is required.",
            },
            {
                "evidence_id": "ev_2",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://demo.edu/blocked",
                "status": "ok",
                "content_quality_status": "blocked",
                "extracted_text": "403 Forbidden",
            },
        ]
        response = {
            "tuition_facts": [],
            "deadline_facts": [],
            "english_requirement_facts": [{"test": "IELTS", "overall_score": 7.0, "supporting_text": "IELTS 7.0 is required.", "confidence_score": 0.9}],
            "cert_requirement_facts": [],
            "application_facts": [],
            "scholarship_facts": [],
            "program_facts": [],
        }

        with tempfile.TemporaryDirectory() as tmp, patch("glowbal_ingestion.llm_extractors.call_openai_structured_extraction") as call:
            out_dir = Path(tmp)
            write_csv(out_dir / "facts.csv", [], [
                "fact_id", "university_id", "program_id", "fact_type", "fact_key", "value_text", "value_json", "value_number", "value_currency", "value_date", "fact_origin", "evidence_id", "source_url", "supporting_text", "confidence_score", "review_status", "extracted_at"
            ])
            call.return_value = response
            facts, report = extract_facts_with_llm(sources, evidence, out_dir, run_id="test", api_key="key")

            self.assertEqual(len(facts), 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(len(report), 2)
            self.assertEqual(read_csv(out_dir / "facts_llm.csv")[0]["supporting_text"], "IELTS 7.0 is required.")


if __name__ == "__main__":
    unittest.main()
