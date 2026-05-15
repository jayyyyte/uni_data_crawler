from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .constants import (
    BATCH_QA_COLUMNS,
    CURRENCY_TO_USD,
    FIELD_GAP_COLUMNS,
    MATCHING_COLUMNS,
    MUST_HAVE_PRODUCT_FIELDS,
    PRODUCT_COLUMNS,
    QUALITY_GATE_COLUMNS,
    QA_COLUMNS,
    REQUIRED_SOURCE_TYPES,
    WRITER_CONTEXT_COLUMNS,
)
from .csv_io import parse_json_cell, write_csv


RAW_SUMMARY_MARKERS = [
    "skip navigation",
    "breadcrumb",
    "search",
    "helpful links",
    "compare programmes",
    "contact us",
    "applicant portal",
    "menu",
]

DATE_TEXT_PATTERN = re.compile(
    r"\b(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?|"
    r"\d{8})\b",
    flags=re.I,
)


def build_profiles(
    seed_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    fact_rows: list[dict[str, str]],
    ranking_rows: list[dict[str, str]],
    out_dir: str | Path,
    country_cost_rows: list[dict[str, str]] | None = None,
    evidence_rows: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    facts_by_university: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fact in fact_rows:
        facts_by_university[fact.get("university_id", "")].append(fact)

    sources_by_university: dict[str, list[dict[str, str]]] = defaultdict(list)
    for source in source_rows:
        sources_by_university[source.get("university_id", "")].append(source)

    evidence_by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for evidence in evidence_rows or []:
        evidence_by_source[evidence.get("source_id", "")].append(evidence)

    rankings_by_university = {row.get("university_id", ""): row for row in ranking_rows}
    country_costs = {row.get("country", ""): row for row in country_cost_rows or []}

    profiles: list[dict[str, object]] = []
    qa_rows: list[dict[str, object]] = []

    for seed in seed_rows:
        university_id = seed.get("university_id", "")
        facts = facts_by_university.get(university_id, [])
        sources = sources_by_university.get(university_id, [])
        ranking = rankings_by_university.get(university_id, {})

        subject_tags = unique_values(facts, "matching", "subject_tag")[:5]
        study_level_tags = unique_values(facts, "matching", "study_level_tag")
        campus_vibe_tags = unique_values(facts, "matching", "campus_vibe_tag")
        support_tags = unique_values(facts, "matching", "support_tag")

        tuition_min, tuition_max = usd_range(facts, "tuition", "tuition_fee")
        living_min, living_max = usd_range(facts, "living_cost", "living_cost")
        country_living_min, country_living_max = country_living_range(seed.get("country", ""), country_costs)
        if living_min == "" or living_max == "" or living_cost_is_suspicious(living_min, living_max):
            living_min, living_max = country_living_min, country_living_max
        total_min = safe_sum(tuition_min, living_min)
        total_max = safe_sum(tuition_max, living_max)

        scholarship_available = bool_value(first_value(facts, "scholarship", "scholarship_available"))
        application_system = first_value(facts, "application", "application_system")
        deadline_summary = deadline_summary_from_candidates(facts)
        english_requirement_summary = english_summary(facts)

        strengths = infer_strengths(subject_tags, support_tags)
        best_for = infer_best_for(subject_tags, study_level_tags, support_tags)
        writer_context = build_writer_context(seed, strengths, best_for, campus_vibe_tags, support_tags)

        evidence_coverage_score = source_coverage_score(sources, evidence_by_source)
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
            "import_status": "",
            "review_status": "needs_review",
        }
        apply_product_validators(profile)
        data_quality_score, missing = data_quality(profile)
        profile["data_quality_score"] = f"{data_quality_score:.2f}"
        profile["import_status"] = import_status_for_profile(profile, missing)
        profile["review_status"] = "draft" if profile["import_status"] != "ready_for_import" else "needs_review"
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
    write_csv(out_path / "batch_qa_report.csv", batch_qa_rows(seed_rows, profiles, sources_by_university, facts_by_university, evidence_by_source), BATCH_QA_COLUMNS)
    write_csv(out_path / "pilot_quality_gate.csv", quality_gate_rows(profiles, qa_rows, fact_rows), QUALITY_GATE_COLUMNS)
    write_csv(out_path / "field_gap_report.csv", field_gap_rows(profiles, qa_rows), FIELD_GAP_COLUMNS)
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


def country_living_range(country: str, country_costs: dict[str, dict[str, str]]) -> tuple[int | str, int | str]:
    row = country_costs.get(country)
    if not row:
        return "", ""
    try:
        return int(row.get("annual_living_usd_min", "")), int(row.get("annual_living_usd_max", ""))
    except ValueError:
        return "", ""


def living_cost_is_suspicious(living_min: int | str, living_max: int | str) -> bool:
    low = to_int(living_min)
    high = to_int(living_max)
    return (low is not None and low > 60000) or (high is not None and high > 60000)


def english_summary(facts: list[dict[str, str]]) -> str:
    values: list[str] = []
    for fact in facts:
        if fact.get("fact_type") != "english_requirement":
            continue
        key = fact.get("fact_key", "")
        if key not in {"IELTS", "TOEFL", "PTE", "Duolingo"}:
            continue
        value = clean_summary_text(fact.get("value_text", ""), 80)
        if value and value not in values:
            values.append(value)
    if not values:
        return ""
    return clean_summary_text(" or ".join(values[:3]), 160)


def deadline_summary_from_candidates(facts: list[dict[str, str]]) -> str:
    values: list[str] = []
    for fact in facts:
        if fact.get("fact_type") != "application" or fact.get("fact_key") != "application_deadline_candidate":
            continue
        payload = parse_json_cell(fact.get("value_json", ""))
        if not isinstance(payload, dict):
            continue
        date_text = clean_summary_text(str(payload.get("date_text", "")), 40)
        if not date_text or not DATE_TEXT_PATTERN.search(date_text):
            continue
        round_name = clean_summary_text(str(payload.get("round_name", "")), 40).title()
        label = round_name or "Deadline"
        value = f"{label}: {date_text}"
        if value not in values:
            values.append(value)
    return clean_summary_text("; ".join(values[:3]), 180)


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


def clean_summary_text(value: str, max_length: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" ;,.:-")
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if any(marker in lowered for marker in RAW_SUMMARY_MARKERS):
        return ""
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(" ", 1)[0].strip(" ;,.:-")
    return cleaned


def apply_product_validators(profile: dict[str, object]) -> None:
    tuition_min = to_int(profile.get("tuition_usd_min"))
    tuition_max = to_int(profile.get("tuition_usd_max"))
    if tuition_min is not None and tuition_min < 500:
        profile["tuition_usd_min"] = ""
        profile["tuition_usd_max"] = ""
    if tuition_max is not None and tuition_max > 120000:
        profile["tuition_usd_min"] = ""
        profile["tuition_usd_max"] = ""

    living_min = to_int(profile.get("living_cost_usd_min"))
    if living_min is not None and living_min > 60000:
        profile["living_cost_usd_min"] = ""
        profile["living_cost_usd_max"] = ""

    deadline = clean_summary_text(str(profile.get("deadline_summary", "")), 180)
    profile["deadline_summary"] = deadline if DATE_TEXT_PATTERN.search(deadline) else ""

    english = clean_summary_text(str(profile.get("english_requirement_summary", "")), 160)
    profile["english_requirement_summary"] = english if has_valid_english_score(english) else ""

    profile["requirement_summary"] = clean_summary_text(
        compact_join([str(profile.get("deadline_summary", "")), str(profile.get("english_requirement_summary", ""))]),
        280,
    )

    total_min = safe_sum(profile.get("tuition_usd_min", ""), profile.get("living_cost_usd_min", ""))
    total_max = safe_sum(profile.get("tuition_usd_max", ""), profile.get("living_cost_usd_max", ""))
    profile["total_cost_usd_min"] = total_min
    profile["total_cost_usd_max"] = total_max


def to_int(value: object) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def has_valid_english_score(value: str) -> bool:
    patterns = [
        r"\bIELTS\s+[4-9](?:\.\d)?\b",
        r"\bTOEFL\s+(?:[4-9]\d|1[01]\d|120)\b",
        r"\bPTE\s+(?:[3-8]\d|90)\b",
        r"\bDuolingo\s+(?:[6-9]\d|1[0-5]\d|160)\b",
    ]
    return any(re.search(pattern, value, flags=re.I) for pattern in patterns)


def import_status_for_profile(profile: dict[str, object], missing: list[str]) -> str:
    if not missing:
        return "ready_for_import"
    has_identity = all(profile.get(field) for field in ["display_name", "country", "city", "website_url", "type"])
    has_matching = bool(profile.get("subject_tags")) and bool(profile.get("study_level_tags"))
    has_budget_context = bool(profile.get("living_cost_usd_min")) and bool(profile.get("living_cost_usd_max"))
    if has_identity and has_matching and has_budget_context:
        return "internal_preview"
    if has_identity:
        return "identity_only"
    return "do_not_import"


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


def source_coverage_score(sources: list[dict[str, str]], evidence_by_source: dict[str, list[dict[str, str]]] | None = None) -> float:
    usable_types = {
        source.get("source_type", "")
        for source in sources
        if source.get("status", "") in {"fetched", "manual"} and source_has_usable_evidence(source, evidence_by_source)
    }
    return len(usable_types & REQUIRED_SOURCE_TYPES) / len(REQUIRED_SOURCE_TYPES)


def source_has_usable_evidence(source: dict[str, str], evidence_by_source: dict[str, list[dict[str, str]]] | None) -> bool:
    if evidence_by_source is None:
        return True
    rows = evidence_by_source.get(source.get("source_id", ""), [])
    if not rows:
        return False
    return any((row.get("content_quality_status") or "usable") == "usable" for row in rows)


def data_quality(profile: dict[str, object]) -> tuple[float, list[str]]:
    missing: list[str] = []
    scorable_fields = [field for field in MUST_HAVE_PRODUCT_FIELDS if field != "data_quality_score"]
    for field in scorable_fields:
        value = profile.get(field)
        if value in ("", None, []):
            missing.append(field)
    score = (len(scorable_fields) - len(missing)) / len(scorable_fields)
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


def field_gap_rows(profiles: list[dict[str, object]], qa_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    profiles_by_id = {str(profile.get("university_id", "")): profile for profile in profiles}
    rows: list[dict[str, object]] = []
    for qa_row in qa_rows:
        university_id = str(qa_row.get("university_id", ""))
        profile = profiles_by_id.get(university_id, {})
        missing = qa_row.get("missing_must_have_fields", [])
        if isinstance(missing, str):
            missing_fields = [part.strip(" '[]") for part in missing.split(",") if part.strip(" '[]")]
        else:
            missing_fields = list(missing)
        for field in missing_fields:
            rows.append(
                {
                    "university_id": university_id,
                    "display_name": profile.get("display_name", qa_row.get("name", "")),
                    "missing_field": field,
                    "import_status": profile.get("import_status", ""),
                }
            )
    return rows


def gate_row(metric: str, value: float, threshold: float, notes: str) -> dict[str, object]:
    rounded_value = round(value, 2)
    rounded_threshold = round(threshold, 2)
    return {
        "metric": metric,
        "value": f"{rounded_value:.2f}",
        "threshold": f"{rounded_threshold:.2f}",
        "status": "pass" if rounded_value >= rounded_threshold else "fail",
        "notes": notes,
    }


def batch_qa_rows(
    seed_rows: list[dict[str, str]],
    profiles: list[dict[str, object]],
    sources_by_university: dict[str, list[dict[str, str]]],
    facts_by_university: dict[str, list[dict[str, str]]],
    evidence_by_source: dict[str, list[dict[str, str]]],
) -> list[dict[str, object]]:
    profiles_by_id = {str(profile.get("university_id", "")): profile for profile in profiles}
    rows: list[dict[str, object]] = []
    for seed in seed_rows:
        university_id = seed.get("university_id", "")
        sources = sources_by_university.get(university_id, [])
        facts = facts_by_university.get(university_id, [])
        evidence = [row for source in sources for row in evidence_by_source.get(source.get("source_id", ""), [])]
        profile = profiles_by_id.get(university_id, {})
        usable_count = sum((row.get("content_quality_status") or "usable") == "usable" for row in evidence)
        blocked_count = sum((row.get("content_quality_status") or "") in {"blocked", "js_challenge", "too_short", "not_found", "low_signal"} for row in evidence)
        failed_count = sum(source.get("status") == "failed" for source in sources)
        tuition_count = count_facts(facts, "tuition", None)
        valid_tuition_count = count_facts(facts, "tuition", "tuition_fee")
        deadline_count = count_facts(facts, "application", None)
        valid_deadline_count = count_facts(facts, "application", "application_deadline_candidate")
        english_count = count_facts(facts, "english_requirement", None)
        valid_english_count = sum(
            1
            for fact in facts
            if fact.get("fact_type") == "english_requirement" and not fact.get("fact_key", "").endswith("_subscore")
        )
        matching_count = count_facts(facts, "matching", None)
        qa_status, qa_notes = qa_status_for_profile(profile, failed_count, valid_tuition_count, valid_deadline_count, valid_english_count)
        rows.append(
            {
                "university_id": university_id,
                "display_name": seed.get("name", ""),
                "source_count": len(sources),
                "usable_evidence_count": usable_count,
                "blocked_evidence_count": blocked_count,
                "failed_source_count": failed_count,
                "tuition_fact_count": tuition_count,
                "valid_tuition_fact_count": valid_tuition_count,
                "deadline_fact_count": deadline_count,
                "valid_deadline_fact_count": valid_deadline_count,
                "english_fact_count": english_count,
                "valid_english_fact_count": valid_english_count,
                "matching_tag_count": matching_count,
                "has_product_profile": bool(profile),
                "import_status": profile.get("import_status", ""),
                "qa_status": qa_status,
                "qa_notes": qa_notes,
            }
        )
    return rows


def count_facts(facts: list[dict[str, str]], fact_type: str, fact_key: str | None) -> int:
    return sum(1 for fact in facts if fact.get("fact_type") == fact_type and (fact_key is None or fact.get("fact_key") == fact_key))


def qa_status_for_profile(
    profile: dict[str, object],
    failed_source_count: int,
    valid_tuition_count: int,
    valid_deadline_count: int,
    valid_english_count: int,
) -> tuple[str, str]:
    if not profile:
        return "do_not_import", "no product profile"
    import_status = str(profile.get("import_status", ""))
    if import_status == "ready_for_import":
        return "ready_for_internal_preview", "validated profile fields present"
    if import_status == "internal_preview":
        return "ready_for_internal_preview", "usable for internal product review"
    if failed_source_count >= 4:
        return "needs_source_repair", "multiple failed sources"
    if valid_tuition_count == 0 or valid_deadline_count == 0 or valid_english_count == 0:
        return "needs_fact_repair", "missing validated tuition/deadline/English facts"
    return "ready_for_internal_preview", "minimum validated facts present"
