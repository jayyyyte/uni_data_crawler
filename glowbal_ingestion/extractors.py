from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import (
    APPLICATION_SYSTEM_KEYWORDS,
    FACT_COLUMNS,
    PROGRAM_COLUMNS,
    STUDY_LEVEL_KEYWORDS,
    SUBJECT_KEYWORDS,
    SUPPORT_KEYWORDS,
    VIBE_KEYWORDS,
)
from .csv_io import write_csv
from .ids import stable_id

MONEY_PATTERN = re.compile(
    r"(?P<currency>US\$|C\$|A\$|S\$|HK\$|USD|GBP|EUR|CAD|AUD|SGD|HKD|JPY|CNY|RMB|CHF|[$£€¥])\s?"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d{4,6})(?:\s?(?:-|to|–|—)\s?"
    r"(?P<currency2>US\$|C\$|A\$|S\$|HK\$|USD|GBP|EUR|CAD|AUD|SGD|HKD|JPY|CNY|RMB|CHF|[$£€¥])?\s?"
    r"(?P<amount2>\d{1,3}(?:,\d{3})+|\d{4,6}))?",
    flags=re.I,
)

IELTS_PATTERN = re.compile(r"IELTS[^.\n]{0,80}?(?P<score>[5-9](?:\.\d)?)", flags=re.I)
TOEFL_PATTERN = re.compile(r"TOEFL[^.\n]{0,80}?(?P<score>\d{2,3})", flags=re.I)
PTE_PATTERN = re.compile(r"\bPTE\b[^.\n]{0,80}?(?P<score>\d{2,3})", flags=re.I)
DEADLINE_PATTERN = re.compile(
    r"((?:deadline|apply by|applications? close|closing date)[^.\n]{0,160})",
    flags=re.I,
)


def extract_facts(
    source_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    out_dir: str | Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    sources_by_id = {row.get("source_id", ""): row for row in source_rows}
    facts: list[dict[str, object]] = []
    programs: list[dict[str, object]] = []

    for evidence in evidence_rows:
        if evidence.get("status") != "ok":
            continue
        source = sources_by_id.get(evidence.get("source_id", ""), {})
        source_type = source.get("source_type", "")
        text = evidence.get("extracted_text", "")

        facts.extend(extract_common_tags(evidence, text))

        if source_type == "tuition_fees":
            facts.extend(extract_money_facts(evidence, text, "tuition", "annual_fee_range"))
        elif source_type == "cost_of_living":
            facts.extend(extract_money_facts(evidence, text, "living_cost", "annual_living_cost_range"))
        elif source_type == "english_requirements":
            facts.extend(extract_english_requirements(evidence, text))
        elif source_type in {"undergraduate_admissions", "graduate_admissions", "international_admissions"}:
            facts.extend(extract_application_facts(evidence, text))
        elif source_type == "scholarships":
            facts.extend(extract_scholarship_facts(evidence, text))
        elif source_type == "program_catalog":
            facts.extend(extract_program_catalog_facts(evidence, text))
            programs.extend(extract_program_rows(evidence, text))
        elif source_type == "housing":
            facts.extend(keyword_fact(evidence, "support", "housing_support", ["housing", "accommodation", "residence"], text))
        elif source_type == "career":
            facts.extend(keyword_fact(evidence, "support", "career_services", ["career", "employability", "internship"], text))

    facts.sort(key=lambda row: (str(row.get("university_id", "")), str(row.get("fact_type", "")), str(row.get("fact_key", "")), str(row.get("source_url", ""))))
    programs.sort(key=lambda row: (str(row.get("university_id", "")), str(row.get("name", ""))))
    write_csv(Path(out_dir) / "facts.csv", facts, FACT_COLUMNS)
    write_csv(Path(out_dir) / "programs.csv", programs, PROGRAM_COLUMNS)
    return facts, programs


def make_fact(
    evidence: dict[str, str],
    fact_type: str,
    fact_key: str,
    value_text: str = "",
    value_json: object | None = None,
    value_number: object = "",
    value_currency: str = "",
    value_date: str = "",
    confidence_score: float = 0.7,
    review_status: str = "needs_review",
) -> dict[str, object]:
    value_json_text = json.dumps(value_json, ensure_ascii=False, sort_keys=True) if value_json is not None else ""
    return {
        "fact_id": stable_id("fact", evidence.get("evidence_id"), fact_type, fact_key, value_text, value_json_text, value_number),
        "university_id": evidence.get("university_id", ""),
        "program_id": "",
        "fact_type": fact_type,
        "fact_key": fact_key,
        "value_text": value_text,
        "value_json": value_json_text,
        "value_number": value_number,
        "value_currency": value_currency,
        "value_date": value_date,
        "evidence_id": evidence.get("evidence_id", ""),
        "source_url": evidence.get("url", ""),
        "confidence_score": f"{confidence_score:.2f}",
        "review_status": review_status,
        "extracted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def extract_common_tags(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    lowered = text.lower()
    for tag, keywords in SUBJECT_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "subject_tag", tag, confidence_score=0.65))
    for tag, keywords in STUDY_LEVEL_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "study_level_tag", tag, confidence_score=0.65))
    for tag, keywords in VIBE_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "campus_vibe_tag", tag, confidence_score=0.45, review_status="generated"))
    for tag, keywords in SUPPORT_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "support_tag", tag, confidence_score=0.6))
    return facts


def extract_money_facts(evidence: dict[str, str], text: str, fact_type: str, fact_key: str) -> list[dict[str, object]]:
    matches = list(MONEY_PATTERN.finditer(text))
    facts: list[dict[str, object]] = []
    for match in matches[:12]:
        currency = normalize_currency(match.group("currency"))
        amount = parse_amount(match.group("amount"))
        amount2 = parse_amount(match.group("amount2") or "")
        values = [value for value in [amount, amount2] if value]
        if not values:
            continue
        min_value = min(values)
        max_value = max(values)
        raw_text = match.group(0)
        facts.append(
            make_fact(
                evidence,
                fact_type,
                fact_key,
                value_text=raw_text,
                value_json={"min": min_value, "max": max_value, "currency": currency},
                value_number=min_value,
                value_currency=currency,
                confidence_score=0.62,
            )
        )
    return facts


def extract_english_requirements(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for label, pattern in [("IELTS", IELTS_PATTERN), ("TOEFL", TOEFL_PATTERN), ("PTE", PTE_PATTERN)]:
        match = pattern.search(text)
        if match:
            score = match.group("score")
            facts.append(
                make_fact(
                    evidence,
                    "english_requirement",
                    label,
                    value_text=f"{label} {score}",
                    value_json={"test": label, "overall": score},
                    value_number=score,
                    confidence_score=0.72,
                )
            )
    return facts


def extract_application_facts(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    lowered = text.lower()
    for system, keywords in APPLICATION_SYSTEM_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "application", "application_system", system, confidence_score=0.7))
            break
    if "rolling admission" in lowered or "rolling admissions" in lowered:
        facts.append(make_fact(evidence, "application", "rolling_admission", "true", confidence_score=0.75))
    for match in DEADLINE_PATTERN.finditer(text):
        facts.append(make_fact(evidence, "application", "deadline_summary", clean_sentence(match.group(1)), confidence_score=0.55))
        break
    return facts


def extract_scholarship_facts(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    lowered = text.lower()
    facts = keyword_fact(evidence, "support", "scholarship", ["scholarship", "financial aid", "bursary", "grant"], text)
    if facts:
        facts.append(make_fact(evidence, "scholarship", "scholarship_available", "true", confidence_score=0.68))
    elif "no scholarship" in lowered or "not offer scholarships" in lowered:
        facts.append(make_fact(evidence, "scholarship", "scholarship_available", "false", confidence_score=0.55))
    return facts


def extract_program_catalog_facts(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    lowered = text.lower()
    for subject, keywords in SUBJECT_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "program", "field_of_study", subject, confidence_score=0.58))
    for level, keywords in STUDY_LEVEL_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "program", "degree_level", level, confidence_score=0.58))
    return facts


def extract_program_rows(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    snippets = re.findall(r"((?:Bachelor|Master|MSc|MA|BSc|PhD|MBA)[^.;:\n]{3,80})", text, flags=re.I)
    for snippet in snippets[:20]:
        name = clean_sentence(snippet)
        rows.append(
            {
                "program_id": stable_id("program", evidence.get("university_id"), name),
                "university_id": evidence.get("university_id", ""),
                "name": name,
                "normalized_name": name.lower(),
                "degree_level": infer_first_tag(name, STUDY_LEVEL_KEYWORDS),
                "field_of_study": infer_first_tag(name, SUBJECT_KEYWORDS),
                "faculty": "",
                "campus": "",
                "language_of_instruction": "",
                "program_url": evidence.get("url", ""),
                "status": "needs_review",
            }
        )
    return rows


def keyword_fact(
    evidence: dict[str, str],
    fact_type: str,
    fact_key: str,
    keywords: list[str],
    text: str,
) -> list[dict[str, object]]:
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            return [make_fact(evidence, fact_type, fact_key, keyword, confidence_score=0.62)]
    return []


def contains_any(lowered_text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in lowered_text for keyword in keywords)


def parse_amount(value: str) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def normalize_currency(value: str) -> str:
    upper = value.upper()
    mapping = {
        "$": "USD",
        "US$": "USD",
        "£": "GBP",
        "€": "EUR",
        "¥": "JPY",
        "C$": "CAD",
        "A$": "AUD",
        "S$": "SGD",
        "HK$": "HKD",
        "RMB": "CNY",
    }
    return mapping.get(upper, upper)


def clean_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .;:-")


def infer_first_tag(text: str, taxonomy: dict[str, list[str]]) -> str:
    lowered = text.lower()
    for tag, keywords in taxonomy.items():
        if contains_any(lowered, keywords):
            return tag
    return ""

