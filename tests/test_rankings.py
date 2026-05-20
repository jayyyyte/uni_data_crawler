from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.csv_io import write_csv
from glowbal_ingestion.rankings import (
    match_rankings,
    normalize_name,
    normalize_qs_rankings_file,
    parse_rank_numeric,
)


class RankingTests(unittest.TestCase):
    def test_parse_rank_numeric_handles_qs_display_forms(self) -> None:
        self.assertEqual(parse_rank_numeric("1"), 1)
        self.assertEqual(parse_rank_numeric("=17"), 17)
        self.assertEqual(parse_rank_numeric("501-550"), 501)
        self.assertEqual(parse_rank_numeric("1201+"), 1201)
        self.assertEqual(parse_rank_numeric(""), "")

    def test_normalize_name_removes_punctuation_parentheses_and_accents(self) -> None:
        self.assertEqual(normalize_name("École Polytechnique (Paris)"), "ecole polytechnique")
        self.assertEqual(normalize_name("King’s College London"), "king s college london")

    def test_match_rankings_auto_matches_alias_and_writes_report(self) -> None:
        seed = [
            {
                "university_id": "mit",
                "name": "Massachusetts Institute of Technology",
                "local_name": "",
                "country": "United States",
                "city": "Cambridge",
            }
        ]
        qs = [
            {
                "institution_name": "Massachusetts Institute of Technology (MIT)",
                "country": "United States",
                "city": "Cambridge",
                "rank_raw": "1",
                "rank_numeric": "1",
                "rank_display": "QS 2026 #1",
                "ranking_source_url": "https://www.topuniversities.com/world-university-rankings",
                "retrieved_at": "2026-05-18",
                "review_status": "approved",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "rankings_import.csv"
            report = Path(tmp) / "ranking_match_report.csv"
            output, report_rows, candidates = match_rankings(seed, qs, [], out, report)

            self.assertEqual(output[0]["qs_rank"], "1")
            self.assertEqual(report_rows[0]["match_status"], "matched")
            self.assertEqual(candidates[0]["review_status"], "approved")
            self.assertEqual(read_csv(out)[0]["rank_display"], "QS 2026 #1")

    def test_match_rankings_flags_ambiguous_candidates(self) -> None:
        seed = [
            {
                "university_id": "demo",
                "name": "University of York",
                "local_name": "",
                "country": "",
                "city": "York",
            }
        ]
        qs = [
            {
                "institution_name": "University of York",
                "country": "United Kingdom",
                "city": "York",
                "rank_raw": "100",
                "rank_numeric": "100",
                "rank_display": "QS 2026 #100",
                "ranking_source_url": "https://www.topuniversities.com/world-university-rankings",
                "retrieved_at": "2026-05-18",
                "review_status": "approved",
            },
            {
                "institution_name": "York University",
                "country": "Canada",
                "city": "Toronto",
                "rank_raw": "101",
                "rank_numeric": "101",
                "rank_display": "QS 2026 #101",
                "ranking_source_url": "https://www.topuniversities.com/world-university-rankings",
                "retrieved_at": "2026-05-18",
                "review_status": "approved",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output, report_rows, _ = match_rankings(seed, qs, [], Path(tmp) / "rankings_import.csv", Path(tmp) / "ranking_match_report.csv")

            self.assertEqual(output[0]["qs_rank"], "")
            self.assertEqual(report_rows[0]["match_status"], "ambiguous")

    def test_existing_rank_is_preserved_when_new_match_is_not_confident(self) -> None:
        seed = [{"university_id": "demo", "name": "Demo College", "local_name": "", "country": "United States", "city": ""}]
        qs = [
            {
                "institution_name": "Different University",
                "country": "United States",
                "city": "",
                "rank_raw": "10",
                "rank_numeric": "10",
                "rank_display": "QS 2026 #10",
                "ranking_source_url": "https://www.topuniversities.com/world-university-rankings",
                "retrieved_at": "2026-05-18",
                "review_status": "approved",
            }
        ]
        base = [{"university_id": "demo", "qs_rank": "99", "rank_display": "QS 2026 #99", "ranking_source_url": "old", "review_status": "approved"}]
        with tempfile.TemporaryDirectory() as tmp:
            output, report_rows, _ = match_rankings(seed, qs, base, Path(tmp) / "rankings_import.csv", Path(tmp) / "ranking_match_report.csv")

            self.assertEqual(output[0]["qs_rank"], "99")
            self.assertEqual(report_rows[0]["match_status"], "existing_preserved")

    def test_normalize_qs_rankings_file_accepts_flexible_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "official_qs_export.csv"
            write_csv(
                source,
                [{"2026 Rank": "=17", "University Name": "University of California, Berkeley", "Country/Territory": "United States"}],
                ["2026 Rank", "University Name", "Country/Territory"],
            )

            raw_rows, normalized_rows = normalize_qs_rankings_file(source, Path(tmp) / "rankings")

            self.assertEqual(raw_rows[0]["institution_name"], "University of California, Berkeley")
            self.assertEqual(normalized_rows[0]["rank_numeric"], 17)
            self.assertEqual(normalized_rows[0]["rank_display"], "QS 2026 #=17")

    def test_normalize_qs_rankings_file_skips_qs_preamble_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "official_qs_export.csv"
            source.write_text(
                "2026 QS World University Rankings,,,,note\n"
                ",2026,2025,Institution,Location\n"
                "Index,Rank,Previous Rank,Name,Country/Territory\n"
                "1,1,1,Massachusetts Institute of Technology (MIT),United States of America\n",
                encoding="utf-8",
            )

            raw_rows, normalized_rows = normalize_qs_rankings_file(source, Path(tmp) / "rankings")

            self.assertEqual(raw_rows[0]["institution_name"], "Massachusetts Institute of Technology (MIT)")
            self.assertEqual(normalized_rows[0]["rank_numeric"], 1)


if __name__ == "__main__":
    unittest.main()
