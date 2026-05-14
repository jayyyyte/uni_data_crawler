from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .constants import (
    CURRENCY_TO_USD,
    MATCHING_COLUMNS,
    MUST_HAVE_PRODUCT_FIELDS,
    PRODUCT_COLUMNS,
    QUALITY_GATE_COLUMNS,
    QA_COLUMNS,
    REQUIRED_SOURCE_TYPES,
    WRITER_CONTEXT_COLUMNS,
)
from .csv_io import parse_json_cell, write_csv


def build_profiles(
    seed_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    fact_rows: list[dict[str, str]],
    ranking_rows: list[dict[str, str]],
    out_dir: str | Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    facts_by_university: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fact in fact_rows:
        facts_by_university[fact.get("university_id", "")].append(fact)

    sources_by_university: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source in source_rows:
        sources_by_university[source.get("university_id", "")].append(source)

    rankings_by_university = {row.get("university_id", ""): row for row in ranking_rows}

    profiles: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []

    for seed in seed_rows:
        university_id = seed.get("university_id", "")
        facts = facts_by_university.get(university_id, [])
        sources = sources_by_university.get(university_id, [])
        ranking = rankings_by_university.get(university_id, {})

        subject_tags = unique_values(facts, "matching", "subject_tag")
        study_level_tags = unique_values(facts, "matching", "study_level_tag")
        campus_vibe_tags = unique_values(facts, "matching", "campus_vibe_tag")
        support_tags = unique_values(facts, "matching", "support_tag")

        tuition_min, tuition_max = usd_range(facts, "tuition", "annual_fee_range")
        living_min, living_max = usd_range(facts, "living_cost", "annual_living_cost_range")
        total_min = safe_sum(tuition_min, living_min)
        total_max = safe_sum(tuition_max, living_max)

        scholarship_available = bool_value(first_value(facts, "scholarship", "scholarship_available"))
        application_system = first_value(facts, "application", "application_system")
        deadline_summary = first_value(facts, "application", "deadline_summary")
        english_requirement_summary = english_summary(facts)

        strengths = infer_strengths(subject_tags, support_tags)
        best_for = infer_best_for(subject_tags, study_level_tags, support_tags)
        writer_context = build_writer_context(seed, strengths, best_for, campus_vibe_tags, support_tags)

        evidence_coverage_score = source_coverage_score(sources)
        profile = {
            "university_id": university_id,
            "display_name": seed.get("name", ""),
            "local_name": seed.get("local_name", ""),
            "country": seed.get("country", ""),
            "city": seed.get("city", ""),
            "region": seed.get("region", ""),
            "country_group": seed.get("country_group", ""),
            "type": seed.get("type", ""),
            "website_url": seed.get("website_url", ""),
            "image_url": "",
            "short_description": "",
            "qs_rank": ranking.get("qs_rank", ""),
            "the_rank": ranking.get("the_rank", ""),
            "arwu_rank": ranking.get("arwu_rank", ""),
            "rank_display": ranking.get("rank_display", ""),
            "subject_tags": subject_tags,
            "study_level_tags": study_level_tags,
            "campus_vibe_tags": campus_vibe_tags,
            "support_tags": support_tags,
            "tuition_usd_min": tuition_min,
            "tuition_usd_max": tuition_max,
            "living_cost_usd_min": living_min,
            "living_cost_usd_max": living_max,
            "total_cost_usd_min": total_min,
            "total_cost_usd_max": total_max,
            "scholarship_available": scholarship_available if scholarship_available is not None else "",
            "application_system": application_system,
            "deadline_summary": deadline_summary,
            "english_requirement_summary": english_requirement_summary,
            "requirement_summary": compact_join([deadline_summary, english_requirement_summary]),
            "strengths": strengths,
            "best_for": best_for,
            "weaknesses": [],
            "writer_context": writer_context,
            "evidence_coverage_score": f"{evidence_coverage_score:.2f}",
            "data_quality_score": "",
            "review_status": "needs_review",
        }
        data_quality_score, missing = data_quality(profile)
        profile["data_quality_score"] = f"{data_quality_score:.2f}"
        profile["review_status"] = "draft" if missing else "needs_review"
        profiles.append(profile)

        qa_rows.append(
            {
                "university_id": university_id,
                "name": seed.get("name", ""),
                "source_count": len(sources),
                "required_source_coverage": f"{evidence_coverage_score:.2f}",
                "evidence_count": len({fact.get("evidence_id", "") for fact in facts if fact.get("evidence_id", "")}),
                "fact_count": len(facts),
                "missing_must_have_fields": missing,
                "evidence_coverage_score": f"{evidence_coverage_score:.2f}",
                "data_quality_score": f"{data_quality_score:.2f}",
                "review_status": profile["review_status"],
            }
        )

    profiles.sort(key=lambda row: str(row.get("university_id", "")))
    qa_rows.sort(key=lambda row: str(row.get("university_id", "")))

    out_path = Path(out_dir)
    write_csv(out_path / "university_product_profiles.csv", profiles, PRODUCT_COLUMNS)
    write_csv(out_path / "university_matching_tags.csv", profiles, MATCHING_COLUMNS)
    write_csv(out_path / "university_writer_context.csv", profiles, WRITER_CONTEXT_COLUMNS)
    write_csv(out_path / "universities_import.csv", profiles, PRODUCT_COLUMNS)
    write_csv(out_path / "qa_report.csv", qa_rows, QA_COLUMNS)
    write_csv(out_path / "pilot_quality_gate.csv", quality_gate_rows(profiles, qa_rows, fact_rows), QUALITY_GATE_COLUMNS)
    return profiles, qa_rows


def unique_values(facts: list[dict[str, str]], fact_type: str, fact_key: str) -> list[str]:
    values = {
        fact.get("value_text", "")
        for fact in facts
        if fact.get("fact_type") == fact_type and fact.get("fact_key") == fact_key and fact.get("value_text")
    }
    return sorted(values)


def first_value(facts: list[dict[str, str]], fact_type: str, fact_key: str) -> str:
    values = [
        fact.get("value_text", "")
        for fact in facts
        if fact.get("fact_type") == fact_type and fact.get("fact_key") == fact_key and fact.get("value_text")
    ]
    return values[0] if values else ""


def usd_range(facts: list[dict[str, str]], fact_type: str, fact_key: str) -> tuple[int | str, int | str]:
    lows: list[int] = []
    highs: list[int] = []
    for fact in facts:
        if fact.get("fact_type") != fact_type or fact.get("fact_key") != fact_key:
            continue
        payload = parse_json_cell(fact.get("value_json", ""))
        if not isinstance(payload, dict):
            continue
        currency = str(payload.get("currency", "USD")).upper()
        rate = CURRENCY_TO_USD.get(currency)
        if rate is None:
            continue
        try:
            low = int(round(float(payload.get("min")) * rate))
            high = int(round(float(payload.get("max")) * rate))
        except (TypeError, ValueError):
            continue
        lows.append(low)
        highs.append(high)
    if not lows or not highs:
        return "", ""
    return min(lows), max(highs)


def english_summary(facts: list[dict[str, str]]) -> str:
    values = [
        fact.get("value_text", "")
        for fact in facts
        if fact.get("fact_type") == "english_requirement" and fact.get("value_text")
    ]
    return compact_join(values)


def bool_value(value: str) -> bool | None:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def safe_sum(left: int | str, right: int | str) -> int | str:
    if left == "" or right == "":
        return ""
    return int(left) + int(right)


def compact_join(values: list[str]) -> str:
    unique = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return "; ".join(unique)


def infer_strengths(subject_tags: list[str], support_tags: list[str]) -> list[str]:
    strengths = subject_tags[:5]
    if "career_services" in support_tags:
        strengths.append("career_support")
    if "scholarship" in support_tags:
        strengths.append("scholarship_options")
    return sorted(set(strengths))


def infer_best_for(subject_tags: list[str], study_level_tags: list[str], support_tags: list[str]) -> list[str]:
    best_for = []
    if subject_tags:
        best_for.append(f"students_interested_in_{subject_tags[0]}")
    if "master" in study_level_tags:
        best_for.append("graduate_applicants")
    if "strong_international_office" in support_tags:
        best_for.append("international_students")
    return sorted(set(best_for))


def build_writer_context(
    seed: dict[str, str],
    strengths: list[str],
    best_for: list[str],
    campus_vibe_tags: list[str],
    support_tags: list[str],
) -> dict[str, object]:
    return {
        "status": "generated_needs_review",
        "why_this_university_points": strengths[:5],
        "student_fit_keywords": best_for[:5],
        "campus_vibe_tags": campus_vibe_tags[:5],
        "support_tags": support_tags[:5],
        "avoid_generic_claims": [
            "Do not claim exact rankings, outcomes, or program details unless the fact is reviewed.",
            "Use the evidence-backed profile fields as context, not as final verified copy.",
        ],
        "source_note": f"Generated from pilot ingestion facts for {seed.get('name', '')}.",
    }


def source_coverage_score(sources: list[dict[str, str]]) -> float:
    usable_types = {
        source.get("source_type", "")
        for source in sources
        if source.get("status", "") in {"fetched", "manual"}
    }
    return len(usable_types & REQUIRED_SOURCE_TYPES) / len(REQUIRED_SOURCE_TYPES)


def data_quality(profile: dict[str, object]) -> tuple[float, list[str]]:
    missing: list[str] = []
    for field in MUST_HAVE_PRODUCT_FIELDS:
        value = profile.get(field)
        if value in ("", None, []):
            missing.append(field)
    score = (len(MUST_HAVE_PRODUCT_FIELDS) - len(missing)) / len(MUST_HAVE_PRODUCT_FIELDS)
    return score, missing


def quality_gate_rows(
    profiles: list[dict[str, object]],
    qa_rows: list[dict[str, object]],
    fact_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    university_count = len(profiles)
    coverage_pass_count = sum(float(row.get("required_source_coverage", 0) or 0) >= 1.0 for row in qa_rows)
    complete_source_rate = coverage_pass_count / university_count if university_count else 0.0

    facts_with_links = sum(1 for fact in fact_rows if fact.get("evidence_id") and fact.get("source_url"))
    fact_link_rate = facts_with_links / len(fact_rows) if fact_rows else 1.0

    average_quality = (
        sum(float(profile.get("data_quality_score", 0) or 0) for profile in profiles) / university_count
        if university_count
        else 0.0
    )

    profiles_with_matching = sum(
        bool(profile.get("subject_tags")) and bool(profile.get("study_level_tags"))
        for profile in profiles
    )
    matching_readiness_rate = profiles_with_matching / university_count if university_count else 0.0

    return [
        gate_row(
            "universities_with_required_sources",
            complete_source_rate,
            0.90,
            "Share of universities with official_home, admissions, tuition_fees, and english_requirements sources fetched/manual.",
        ),
        gate_row(
            "facts_with_evidence_links",
            fact_link_rate,
            1.00,
            "Every emitted fact must have evidence_id and source_url.",
        ),
        gate_row(
            "average_data_quality_score",
            average_quality,
            0.70,
            "Average completeness across pilot must-have fields.",
        ),
        gate_row(
            "matching_readiness_rate",
            matching_readiness_rate,
            0.80,
            "Share of profiles with both subject_tags and study_level_tags.",
        ),
    ]


def gate_row(metric: str, value: float, threshold: float, notes: str) -> dict[str, object]:
    return {
        "metric": metric,
        "value": f"{value:.2f}",
        "threshold": f"{threshold:.2f}",
        "status": "pass" if value >= threshold else "fail",
        "notes": notes,
    }
