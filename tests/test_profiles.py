from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.profiles import build_profiles


class ProfileTests(unittest.TestCase):
    def test_build_profiles_is_deterministic_for_same_inputs(self) -> None:
        seed = [
            {
                "university_id": "demo",
                "name": "Demo University",
                "local_name": "示例大学",
                "country": "Singapore",
                "city": "Singapore",
                "region": "Asia",
                "country_group": "Asia",
                "website_url": "https://example.edu",
                "type": "public",
            }
        ]
        sources = [
            {"university_id": "demo", "source_type": "official_home", "status": "fetched"},
            {"university_id": "demo", "source_type": "undergraduate_admissions", "status": "fetched"},
            {"university_id": "demo", "source_type": "tuition_fees", "status": "fetched"},
            {"university_id": "demo", "source_type": "english_requirements", "status": "fetched"},
        ]
        facts = [
            {
                "university_id": "demo",
                "fact_type": "matching",
                "fact_key": "subject_tag",
                "value_text": "computer_science",
                "value_json": "",
                "evidence_id": "ev_1",
            },
            {
                "university_id": "demo",
                "fact_type": "matching",
                "fact_key": "study_level_tag",
                "value_text": "bachelor",
                "value_json": "",
                "evidence_id": "ev_1",
            },
            {
                "university_id": "demo",
                "fact_type": "tuition",
                "fact_key": "annual_fee_range",
                "value_text": "SGD 30000 to SGD 40000",
                "value_json": '{"currency":"SGD","max":40000,"min":30000}',
                "evidence_id": "ev_2",
            },
            {
                "university_id": "demo",
                "fact_type": "living_cost",
                "fact_key": "annual_living_cost_range",
                "value_text": "SGD 15000 to SGD 20000",
                "value_json": '{"currency":"SGD","max":20000,"min":15000}',
                "evidence_id": "ev_3",
            },
            {
                "university_id": "demo",
                "fact_type": "scholarship",
                "fact_key": "scholarship_available",
                "value_text": "true",
                "value_json": "",
                "evidence_id": "ev_4",
            },
            {
                "university_id": "demo",
                "fact_type": "application",
                "fact_key": "application_system",
                "value_text": "direct",
                "value_json": "",
                "evidence_id": "ev_5",
            },
            {
                "university_id": "demo",
                "fact_type": "application",
                "fact_key": "deadline_summary",
                "value_text": "Deadline is 15 January",
                "value_json": "",
                "evidence_id": "ev_6",
            },
            {
                "university_id": "demo",
                "fact_type": "english_requirement",
                "fact_key": "IELTS",
                "value_text": "IELTS 6.5",
                "value_json": "",
                "evidence_id": "ev_7",
            },
        ]
        rankings = [{"university_id": "demo", "qs_rank": "8", "rank_display": "QS #8"}]

        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_profiles, left_qa = build_profiles(seed, sources, facts, rankings, Path(left_tmp))
            right_profiles, right_qa = build_profiles(seed, sources, facts, rankings, Path(right_tmp))

        self.assertEqual(left_profiles, right_profiles)
        self.assertEqual(left_qa, right_qa)
        self.assertEqual(left_profiles[0]["local_name"], "示例大学")
        self.assertEqual(left_profiles[0]["total_cost_usd_min"], 33300)

    def test_build_profiles_uses_country_living_cost_fallback(self) -> None:
        seed = [
            {
                "university_id": "demo",
                "name": "Demo University",
                "country": "Japan",
                "city": "Tokyo",
                "website_url": "https://demo.jp",
                "type": "public",
            }
        ]
        country_costs = [
            {
                "country": "Japan",
                "annual_living_usd_min": "12000",
                "annual_living_usd_max": "18000",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            profiles, _qa = build_profiles(seed, [], [], [], Path(tmp), country_costs)

        self.assertEqual(profiles[0]["living_cost_usd_min"], 12000)
        self.assertEqual(profiles[0]["living_cost_usd_max"], 18000)


if __name__ == "__main__":
    unittest.main()
