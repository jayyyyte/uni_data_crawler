from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import (
    APPLICATION_SYSTEM_KEYWORDS,
    CERT_REQUIREMENT_PATTERNS,
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
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?|"
    r"\d{8})\b",
    flags=re.I,
)

MONEY_REJECT_KEYWORDS = [
    "application fee",
    "deposit",
    "housing",
    "room",
    "board",
    "meal",
    "books",
    "personal expenses",
    "transportation",
    "financial aid",
    "family income",
    "scholarship",
    "grant",
    "cost of attendance",
    "estimated expenses",
]

MONEY_CLASSIFIERS = {
    "tuition_fee": ["tuition", "tuition fee", "programme fee", "program fee", "annual fee", "international student fee", "non-local student fee", "overseas fee"],
    "living_cost": ["living cost", "cost of living", "living expenses"],
    "housing_cost": ["housing", "room", "accommodation", "residence"],
    "application_fee": ["application fee", "admission fee"],
    "scholarship_amount": ["scholarship", "grant", "bursary"],
    "aid_income_threshold": ["family income", "household income", "income threshold"],
    "total_cost": ["cost of attendance", "total cost"],
}


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
        if evidence.get("content_quality_status") and evidence.get("content_quality_status") != "usable":
            continue
        source = sources_by_id.get(evidence.get("source_id", ""), {})
        source_type = source.get("source_type", "")
        text = evidence.get("extracted_text", "")

        facts.extend(extract_common_tags(evidence, text, source_type))

        if source_type == "tuition_fees":
            facts.extend(extract_money_facts(evidence, text))
        elif source_type == "cost_of_living":
            facts.extend(extract_money_facts(evidence, text, forced_classification="living_cost"))
        elif source_type == "english_requirements":
            facts.extend(extract_english_requirements(evidence, text))
        elif source_type in {"undergraduate_admissions", "graduate_admissions", "international_admissions"}:
            facts.extend(extract_application_facts(evidence, text))
            facts.extend(extract_cert_requirements(evidence, text))
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
    write_csv(Path(out_dir) / "facts_extracted.csv", extracted_fact_rows(facts), FACT_COLUMNS)
    write_csv(Path(out_dir) / "facts_generated.csv", generated_fact_rows(facts), FACT_COLUMNS)
    write_csv(Path(out_dir) / "programs.csv", programs, PROGRAM_COLUMNS)
    return facts, programs


def extracted_fact_rows(facts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [fact for fact in facts if fact.get("fact_origin") in {"extracted_from_source", "manual"}]


def generated_fact_rows(facts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [fact for fact in facts if fact.get("fact_origin") not in {"extracted_from_source", "manual"}]


def make_fact(
    evidence: dict[str, str],
    fact_type: str,
    fact_key: str,
    value_text: str = "",
    value_json: object | None = None,
    value_number: object = "",
    value_currency: str = "",
    value_date: str = "",
    fact_origin: str = "extracted_from_source",
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
        "fact_origin": fact_origin,
        "evidence_id": evidence.get("evidence_id", ""),
        "source_url": evidence.get("url", ""),
        "confidence_score": f"{confidence_score:.2f}",
        "review_status": review_status,
        "extracted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def extract_common_tags(evidence: dict[str, str], text: str, source_type: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    lowered = text.lower()
    if source_type in {"program_catalog", "undergraduate_admissions", "graduate_admissions", "international_admissions"}:
        for tag, keywords in SUBJECT_KEYWORDS.items():
            if contains_any(lowered, keywords):
                facts.append(make_fact(evidence, "matching", "subject_tag", tag, fact_origin="inferred_from_text", confidence_score=0.62))
        for tag, keywords in STUDY_LEVEL_KEYWORDS.items():
            if contains_any(lowered, keywords):
                facts.append(make_fact(evidence, "matching", "study_level_tag", tag, fact_origin="inferred_from_text", confidence_score=0.62))
    for tag, keywords in VIBE_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "campus_vibe_tag", tag, fact_origin="generated_by_rule", confidence_score=0.45, review_status="generated"))
    for tag, keywords in SUPPORT_KEYWORDS.items():
        if contains_any(lowered, keywords):
            facts.append(make_fact(evidence, "matching", "support_tag", tag, fact_origin="inferred_from_text", confidence_score=0.6))
    return facts


def extract_money_facts(evidence: dict[str, str], text: str, forced_classification: str | None = None) -> list[dict[str, object]]:
    matches = list(MONEY_PATTERN.finditer(text))
    facts: list[dict[str, object]] = []
    for match in matches[:40]:
        currency = normalize_currency(match.group("currency"))
        amount = parse_amount(match.group("amount"))
        amount2 = parse_amount(match.group("amount2") or "")
        values = [value for value in [amount, amount2] if value]
        if not values:
            continue
        min_value = min(values)
        max_value = max(values)
        raw_text = match.group(0)
        context = context_window(text, match.start(), match.end())
        classification = forced_classification or classify_money_context(context)
        if classification == "reject":
            continue
        fact_type = "tuition" if classification == "tuition_fee" else classification
        facts.append(
            make_fact(
                evidence,
                fact_type,
                classification,
                value_text=raw_text,
                value_json={"min": min_value, "max": max_value, "currency": currency, "classification": classification, "context": context[:240]},
                value_number=min_value,
                value_currency=currency,
                confidence_score=0.74 if classification == "tuition_fee" else 0.55,
            )
        )
    return facts


def extract_english_requirements(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for label, pattern in [("IELTS", IELTS_PATTERN), ("TOEFL", TOEFL_PATTERN), ("PTE", PTE_PATTERN)]:
        match = pattern.search(text)
        if match:
            score = float(match.group("score"))
            validated = validate_english_score(label, score)
            if validated == "reject":
                continue
            fact_key = label if validated == "overall" else f"{label}_subscore"
            facts.append(
                make_fact(
                    evidence,
                    "english_requirement",
                    fact_key,
                    value_text=f"{label} {match.group('score')}",
                    value_json={"test": label, "overall": score if validated == "overall" else None, "subscore_min": score if validated == "subscore" else None},
                    value_number=score,
                    confidence_score=0.72 if validated == "overall" else 0.48,
                    review_status="needs_review" if validated == "subscore" else "needs_review",
                )
            )
    summary = english_requirement_summary(text)
    if summary:
        facts.append(
            make_fact(
                evidence,
                "english_requirement",
                "summary",
                value_text=summary,
                confidence_score=0.58,
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
    if "portfolio" in lowered:
        facts.append(make_fact(evidence, "application", "portfolio_required", "true", confidence_score=0.62))
    if "interview" in lowered:
        facts.append(make_fact(evidence, "application", "interview_required", "true", confidence_score=0.58))
    for candidate in deadline_candidates(text)[:4]:
        facts.append(
            make_fact(
                evidence,
                "application",
                "application_deadline_candidate",
                value_text=candidate["text"],
                value_json=candidate,
                value_date=candidate.get("parsed_date", ""),
                confidence_score=candidate["confidence"],
            )
        )
    return facts


def extract_cert_requirements(evidence: dict[str, str], text: str) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for cert_key, pattern in CERT_REQUIREMENT_PATTERNS.items():
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        context = context_window(text, match.start(), match.end(), radius=120)
        if cert_context_is_relevant(context, cert_key, match.group(0)):
            facts.append(
                make_fact(
                    evidence,
                    "cert_requirement",
                    cert_key,
                    value_text=cert_key,
                    value_json={"cert": cert_key, "context": context[:240]},
                    confidence_score=cert_confidence(context),
                )
            )
    return facts


def cert_context_is_relevant(context: str, cert_key: str, matched_text: str) -> bool:
    lowered = context.lower()
    if any(keyword in lowered for keyword in ["certificate", "certification authority", "copyright"]):
        return False
    if cert_key in {"ACT", "AP", "IB", "STEP"} and matched_text != matched_text.upper():
        return False
    if cert_key == "STEP" and not any(
        keyword in lowered
        for keyword in ["step mathematics", "sixth term", "admissions test", "admission test", "mathematics test", "mathematical"]
    ):
        return False
    return any(
        keyword in lowered
        for keyword in [
            "required",
            "requirement",
            "admission",
            "apply",
            "application",
            "submit",
            "score",
            "qualification",
            "exam",
            "test",
            "optional",
            "accepted",
        ]
    )


def cert_confidence(context: str) -> float:
    lowered = context.lower()
    if any(keyword in lowered for keyword in ["required", "requirement", "must submit"]):
        return 0.72
    if any(keyword in lowered for keyword in ["optional", "accepted", "may submit"]):
        return 0.60
    return 0.52


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


def context_window(text: str, start: int, end: int, radius: int = 140) -> str:
    return clean_sentence(text[max(0, start - radius) : min(len(text), end + radius)])


def classify_money_context(context: str) -> str:
    lowered = context.lower()
    if any(keyword in lowered for keyword in MONEY_REJECT_KEYWORDS):
        for label, keywords in MONEY_CLASSIFIERS.items():
            if label != "tuition_fee" and any(keyword in lowered for keyword in keywords):
                return label
        return "reject"
    for label, keywords in MONEY_CLASSIFIERS.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return "reject"


def validate_english_score(label: str, score: float) -> str:
    if label == "IELTS":
        return "overall" if 4.0 <= score <= 9.0 else "reject"
    if label == "TOEFL":
        if 40 <= score <= 120:
            return "overall"
        if 0 <= score <= 30:
            return "subscore"
        return "reject"
    if label == "PTE":
        return "overall" if 30 <= score <= 90 else "reject"
    return "reject"


def deadline_candidates(text: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        cleaned = clean_sentence(sentence)
        if "deadline" not in cleaned.lower() and "apply by" not in cleaned.lower():
            continue
        date_match = DATE_PATTERN.search(cleaned)
        if not date_match:
            continue
        candidates.append(
            {
                "date_text": date_match.group(0),
                "parsed_date": "",
                "round_name": infer_round_name(cleaned),
                "degree_level": infer_first_tag(cleaned, STUDY_LEVEL_KEYWORDS),
                "text": cleaned[:500],
                "confidence": 0.72 if infer_round_name(cleaned) else 0.62,
            }
        )
    return candidates


def infer_round_name(text: str) -> str:
    lowered = text.lower()
    if "early" in lowered:
        return "early"
    if "regular" in lowered or "main round" in lowered:
        return "regular"
    if "late" in lowered:
        return "late"
    return ""


def english_requirement_summary(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    candidates = []
    for sentence in sentences:
        cleaned = clean_sentence(sentence)
        lowered = cleaned.lower()
        if not cleaned or len(cleaned) < 30:
            continue
        if any(keyword in lowered for keyword in ["english language", "english proficiency", "toefl", "ielts", "pte", "duolingo"]):
            candidates.append(cleaned)
        if len(candidates) >= 2:
            break
    if not candidates:
        return ""
    summary = " ".join(candidates)
    return summary[:500].rstrip()
