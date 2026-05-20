from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from glowbal_ingestion.csv_io import read_csv, write_csv
from glowbal_ingestion.llm_extractors import extract_facts_with_llm, gemini_response_text, llm_response_to_facts, normalize_llm_response


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

    def test_llm_response_to_facts_gates_fact_types_by_source_type(self) -> None:
        evidence = {
            "evidence_id": "ev_1",
            "university_id": "demo",
            "url": "https://demo.edu/fees",
            "extracted_text": "01 Jun Semester 1 ends. International tuition is USD 45000 per year.",
        }
        source = {"source_type": "tuition_fees"}
        response = {
            "tuition_facts": [{"amount_min": 45000, "amount_max": 45000, "currency": "USD", "supporting_text": "International tuition is USD 45000 per year.", "confidence_score": 0.9}],
            "deadline_facts": [{"date_text": "01 Jun", "supporting_text": "01 Jun Semester 1 ends.", "confidence_score": 0.9}],
            "english_requirement_facts": [],
            "cert_requirement_facts": [],
            "application_facts": [],
            "scholarship_facts": [],
            "program_facts": [],
        }

        facts = llm_response_to_facts(evidence, source, response)

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["fact_type"], "tuition")

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
            facts, report = extract_facts_with_llm(sources, evidence, out_dir, run_id="test", provider="openai", api_key="key")

            self.assertEqual(len(facts), 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(len(report), 2)
            self.assertEqual(read_csv(out_dir / "facts_llm.csv")[0]["supporting_text"], "IELTS 7.0 is required.")

    def test_extract_facts_with_llm_keeps_existing_llm_facts_csv(self) -> None:
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
            }
        ]
        existing_fact = {
            "fact_id": "fact_existing",
            "university_id": "demo",
            "program_id": "",
            "fact_type": "cert_requirement",
            "fact_key": "SAT",
            "value_text": "SAT",
            "value_json": "{}",
            "value_number": "",
            "value_currency": "",
            "value_date": "",
            "fact_origin": "llm_extracted_from_source",
            "evidence_id": "ev_old",
            "source_url": "https://demo.edu/old",
            "supporting_text": "SAT is optional.",
            "confidence_score": "0.70",
            "review_status": "needs_review",
            "extracted_at": "2026-01-01T00:00:00+00:00",
        }
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
            write_csv(out_dir / "facts.csv", [existing_fact], [
                "fact_id", "university_id", "program_id", "fact_type", "fact_key", "value_text", "value_json", "value_number", "value_currency", "value_date", "fact_origin", "evidence_id", "source_url", "supporting_text", "confidence_score", "review_status", "extracted_at"
            ])
            call.return_value = response
            extract_facts_with_llm(sources, evidence, out_dir, run_id="test", provider="openai", api_key="key")

            self.assertEqual(len(read_csv(out_dir / "facts_llm.csv")), 2)

    def test_extract_facts_with_llm_can_use_gemini_provider(self) -> None:
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
            }
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

        with tempfile.TemporaryDirectory() as tmp, patch("glowbal_ingestion.llm_extractors.call_gemini_structured_extraction") as call:
            out_dir = Path(tmp)
            call.return_value = response
            facts, report = extract_facts_with_llm(sources, evidence, out_dir, run_id="test", provider="gemini", api_key="key")

            self.assertEqual(len(facts), 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(report[0]["model"], "gemini-2.5-flash-lite")

    def test_extract_facts_with_llm_filters_source_types_before_limit(self) -> None:
        sources = [
            {"source_id": "src_1", "university_id": "demo", "source_type": "undergraduate_admissions", "url": "https://demo.edu/apply"},
            {"source_id": "src_2", "university_id": "demo", "source_type": "english_requirements", "url": "https://demo.edu/english"},
        ]
        evidence = [
            {
                "evidence_id": "ev_1",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://demo.edu/apply",
                "status": "ok",
                "content_quality_status": "usable",
                "extracted_text": "Apply online.",
            },
            {
                "evidence_id": "ev_2",
                "source_id": "src_2",
                "university_id": "demo",
                "url": "https://demo.edu/english",
                "status": "ok",
                "content_quality_status": "usable",
                "extracted_text": "IELTS 7.0 is required.",
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

        with tempfile.TemporaryDirectory() as tmp, patch("glowbal_ingestion.llm_extractors.call_gemini_structured_extraction") as call:
            call.return_value = response
            facts, report = extract_facts_with_llm(
                sources,
                evidence,
                Path(tmp),
                run_id="test",
                provider="gemini",
                api_key="key",
                limit=1,
                source_types={"english_requirements"},
            )

            self.assertEqual(len(facts), 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(report[0]["error"], "source type filtered")

    def test_extract_facts_with_llm_offset_skips_eligible_rows(self) -> None:
        sources = [
            {"source_id": "src_1", "university_id": "demo", "source_type": "english_requirements", "url": "https://demo.edu/english-1"},
            {"source_id": "src_2", "university_id": "demo", "source_type": "english_requirements", "url": "https://demo.edu/english-2"},
        ]
        evidence = [
            {
                "evidence_id": "ev_1",
                "source_id": "src_1",
                "university_id": "demo",
                "url": "https://demo.edu/english-1",
                "status": "ok",
                "content_quality_status": "usable",
                "extracted_text": "IELTS 6.5 is required.",
            },
            {
                "evidence_id": "ev_2",
                "source_id": "src_2",
                "university_id": "demo",
                "url": "https://demo.edu/english-2",
                "status": "ok",
                "content_quality_status": "usable",
                "extracted_text": "IELTS 7.0 is required.",
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

        with tempfile.TemporaryDirectory() as tmp, patch("glowbal_ingestion.llm_extractors.call_gemini_structured_extraction") as call:
            call.return_value = response
            facts, report = extract_facts_with_llm(
                sources,
                evidence,
                Path(tmp),
                run_id="test",
                provider="gemini",
                api_key="key",
                limit=1,
                offset=1,
                source_types={"english_requirements"},
            )

            self.assertEqual(len(facts), 1)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(report[0]["error"], "llm offset skipped")

    def test_gemini_response_text_parses_candidate_parts(self) -> None:
        data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "{\"tuition_facts\": []}"}
                        ]
                    }
                }
            ]
        }

        self.assertEqual(gemini_response_text(data), "{\"tuition_facts\": []}")

    def test_normalize_llm_response_routes_top_level_arrays(self) -> None:
        response = [
            {"amount_min": 45000, "currency": "USD", "supporting_text": "Tuition is USD 45000."},
            {"date_text": "January 15", "supporting_text": "Apply by January 15."},
            {"test": "IELTS", "overall_score": 7.0, "supporting_text": "IELTS 7.0 is required."},
            {"cert": "SAT", "supporting_text": "SAT is optional."},
        ]

        normalized = normalize_llm_response(response)

        self.assertEqual(len(normalized["tuition_facts"]), 1)
        self.assertEqual(len(normalized["deadline_facts"]), 1)
        self.assertEqual(len(normalized["english_requirement_facts"]), 1)
        self.assertEqual(len(normalized["cert_requirement_facts"]), 1)


if __name__ == "__main__":
    unittest.main()
