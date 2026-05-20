from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import (
    FACT_COLUMNS,
    LLM_EXTRACTION_REPORT_COLUMNS,
    PROGRAM_COLUMNS,
)
from .csv_io import parse_json_cell, read_csv, write_csv
from .extractors import extracted_fact_rows, generated_fact_rows
from .ids import stable_id

OPENAI_CHAT_COMPLETIONS_ENDPOINT = "https://api.openai.com/v1/chat/completions"
GEMINI_GENERATE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
LLM_PROMPT_VERSION = "llm_extractor_v1"
MAX_EVIDENCE_CHARS = 45000
DEFAULT_LLM_REQUEST_TIMEOUT = 180


def extract_facts_with_llm(
    source_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    out_dir: str | Path,
    run_id: str = "",
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    limit: int = 0,
    offset: int = 0,
    sleep_seconds: float = 0.0,
    source_types: set[str] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected_provider = normalize_provider(provider or os.environ.get("LLM_PROVIDER", "openai"))
    key = api_key or api_key_for_provider(selected_provider)
    if not key:
        env_name = "GEMINI_API_KEY" if selected_provider == "gemini" else "OPENAI_API_KEY"
        raise RuntimeError(f"{env_name} is required for extract-facts-llm provider={selected_provider}")
    selected_model = model or model_for_provider(selected_provider)
    sources_by_id = {row.get("source_id", ""): row for row in source_rows}
    out_path = Path(out_dir)
    llm_facts: list[dict[str, object]] = []
    report_rows: list[dict[str, object]] = []
    attempts = 0
    eligible_seen = 0

    for evidence in evidence_rows:
        source = sources_by_id.get(evidence.get("source_id", ""), {})
        if source_types and source.get("source_type", "") not in source_types:
            report_rows.append(report_row(evidence, sources_by_id, "skipped", 0, "source type filtered", selected_model))
            continue
        if evidence.get("status") != "ok" or evidence.get("content_quality_status") != "usable":
            report_rows.append(report_row(evidence, sources_by_id, "skipped", 0, "non-usable evidence", selected_model))
            continue
        if eligible_seen < offset:
            eligible_seen += 1
            report_rows.append(report_row(evidence, sources_by_id, "skipped", 0, "llm offset skipped", selected_model))
            continue
        eligible_seen += 1
        if limit > 0 and attempts >= limit:
            report_rows.append(report_row(evidence, sources_by_id, "skipped", 0, "llm limit reached", selected_model))
            continue
        try:
            attempts += 1
            extracted = normalize_llm_response(call_structured_extraction(evidence, source, selected_provider, selected_model, key))
            facts = llm_response_to_facts(evidence, source, extracted)
            llm_facts.extend(facts)
            report_rows.append(report_row(evidence, sources_by_id, "ok", len(facts), "", selected_model))
        except Exception as exc:  # Keep one-off batch moving and inspect report.
            report_rows.append(report_row(evidence, sources_by_id, "failed", 0, str(exc), selected_model))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    existing_facts = read_csv(out_path / "facts.csv") if (out_path / "facts.csv").exists() else []
    merged_facts = merge_facts(existing_facts, llm_facts)
    existing_programs = read_csv(out_path / "programs.csv") if (out_path / "programs.csv").exists() else []

    write_csv(out_path / "facts_llm.csv", llm_fact_rows(merged_facts), FACT_COLUMNS)
    write_csv(out_path / "facts.csv", merged_facts, FACT_COLUMNS)
    write_csv(out_path / "facts_extracted.csv", extracted_fact_rows(merged_facts), FACT_COLUMNS)
    write_csv(out_path / "facts_generated.csv", generated_fact_rows(merged_facts), FACT_COLUMNS)
    write_csv(out_path / "programs.csv", existing_programs, PROGRAM_COLUMNS)
    write_csv(out_path / "llm_extraction_report.csv", report_rows, LLM_EXTRACTION_REPORT_COLUMNS)
    write_llm_metadata(out_path, run_id, selected_provider, selected_model, len(llm_facts), len(report_rows))
    return llm_facts, report_rows


def normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in {"openai", "gemini"}:
        raise RuntimeError(f"Unsupported LLM provider: {provider}")
    return normalized


def api_key_for_provider(provider: str) -> str:
    if provider == "gemini":
        return os.environ.get("GEMINI_API_KEY", "")
    return os.environ.get("OPENAI_API_KEY", "")


def model_for_provider(provider: str) -> str:
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def call_structured_extraction(
    evidence: dict[str, str],
    source: dict[str, str],
    provider: str,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    if provider == "gemini":
        return call_gemini_structured_extraction(evidence, source, model, api_key)
    return call_openai_structured_extraction(evidence, source, model, api_key)


def call_openai_structured_extraction(
    evidence: dict[str, str],
    source: dict[str, str],
    model: str,
    api_key: str,
) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You extract university admissions facts from provided page text. "
                "Only use values explicitly present in the text. Return null/empty arrays when absent. "
                "Every extracted value must include exact supporting_text copied from the page text."
            ),
        },
        {
            "role": "user",
            "content": build_llm_prompt(evidence, source),
        },
    ]
    payload = {
        "model": model,
        "temperature": 0,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "university_fact_extraction",
                "strict": True,
                "schema": llm_json_schema(),
            },
        },
    }
    request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout_seconds()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI extraction failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI extraction failed: {exc.reason}") from exc
    content = data["choices"][0]["message"].get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI returned malformed JSON") from exc


def call_gemini_structured_extraction(
    evidence: dict[str, str],
    source: dict[str, str],
    model: str,
    api_key: str,
) -> dict[str, Any]:
    prompt = (
        "You extract university admissions facts from provided page text. "
        "Only use values explicitly present in the text. Return valid JSON only. "
        "Every extracted value must include exact supporting_text copied from the page text.\n\n"
        f"{build_llm_prompt(evidence, source)}\n\n"
        "Return JSON with exactly these top-level array keys: "
        "tuition_facts, deadline_facts, english_requirement_facts, cert_requirement_facts, "
        "application_facts, scholarship_facts, program_facts. Use empty arrays when absent."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    endpoint = GEMINI_GENERATE_ENDPOINT.format(model=model, api_key=api_key)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout_seconds()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini extraction failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini extraction failed: {exc.reason}") from exc
    content = gemini_response_text(data)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned malformed JSON") from exc


def gemini_response_text(data: dict[str, Any]) -> str:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini returned no candidates")
    content = candidates[0].get("content", {})
    parts = content.get("parts", []) if isinstance(content, dict) else []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    result = "".join(texts).strip()
    if not result:
        raise RuntimeError("Gemini returned empty content")
    return result


def request_timeout_seconds() -> int:
    try:
        return int(os.environ.get("LLM_REQUEST_TIMEOUT", DEFAULT_LLM_REQUEST_TIMEOUT))
    except ValueError:
        return DEFAULT_LLM_REQUEST_TIMEOUT


def normalize_llm_response(response: object) -> dict[str, Any]:
    empty = {
        "tuition_facts": [],
        "deadline_facts": [],
        "english_requirement_facts": [],
        "cert_requirement_facts": [],
        "application_facts": [],
        "scholarship_facts": [],
        "program_facts": [],
    }
    if isinstance(response, dict):
        normalized = dict(empty)
        for key in empty:
            value = response.get(key, [])
            normalized[key] = value if isinstance(value, list) else []
        if not any(normalized.values()) and isinstance(response.get("facts"), list):
            return normalize_llm_response(response["facts"])
        return normalized
    if not isinstance(response, list):
        return empty

    normalized = dict(empty)
    for item in response:
        if not isinstance(item, dict):
            continue
        nested_keys = [key for key in empty if isinstance(item.get(key), list)]
        if nested_keys:
            for key in nested_keys:
                normalized[key].extend(item[key])
            continue
        target = response_item_target(item)
        if target:
            normalized[target].append(item)
    return normalized


def response_item_target(item: dict[str, Any]) -> str:
    fact_type = str(item.get("fact_type") or item.get("type") or "").strip().lower()
    if fact_type in {"tuition", "tuition_fee"}:
        return "tuition_facts"
    if fact_type in {"deadline", "application_deadline", "application_deadline_candidate"}:
        return "deadline_facts"
    if fact_type in {"english", "english_requirement"}:
        return "english_requirement_facts"
    if fact_type in {"cert", "certificate", "cert_requirement"}:
        return "cert_requirement_facts"
    if fact_type in {"application", "admission"}:
        return "application_facts"
    if fact_type in {"scholarship", "financial_aid"}:
        return "scholarship_facts"
    if fact_type in {"program", "programme"}:
        return "program_facts"
    if item.get("amount_min") not in ("", None) or item.get("currency") not in ("", None):
        return "tuition_facts"
    if item.get("date_text") not in ("", None) or item.get("parsed_date") not in ("", None):
        return "deadline_facts"
    if item.get("test") not in ("", None) or item.get("overall_score") not in ("", None):
        return "english_requirement_facts"
    if item.get("cert") not in ("", None) or item.get("requirement_type") not in ("", None):
        return "cert_requirement_facts"
    if any(item.get(key) not in ("", None, False) for key in ["application_system", "rolling_admission", "portfolio_required", "interview_required"]):
        return "application_facts"
    if item.get("scholarship_available") is not None:
        return "scholarship_facts"
    if item.get("program_name") not in ("", None) or item.get("field_of_study") not in ("", None):
        return "program_facts"
    return ""


def build_llm_prompt(evidence: dict[str, str], source: dict[str, str]) -> str:
    text = evidence.get("extracted_text", "")[:MAX_EVIDENCE_CHARS]
    return f"""Source type: {source.get('source_type', '')}
University id: {evidence.get('university_id', '')}
Source URL: {evidence.get('url', '')}

Extract only evidence-backed facts from this page text.

Classification rules:
- Tuition must be tuition/programme fee/international fee/overseas fee. Do not classify housing, application fee, scholarships, financial aid, family income, cost of attendance, deposits, books, meals, or transport as tuition.
- English requirements are IELTS, TOEFL iBT, PTE, Duolingo, Cambridge English only.
- SAT/ACT/GRE/GMAT/LSAT/MCAT/LNAT/UCAT/BMAT/TMUA/STEP/AP/IB/A-Level/HSK/JLPT/TOPIK are cert requirements, not English requirements.
- Deadlines need a date_text from the page.
- If unsure, omit the fact.

Page text:
{text}
"""


def llm_json_schema() -> dict[str, Any]:
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "display_text": {"type": ["string", "null"]},
            "supporting_text": {"type": ["string", "null"]},
            "confidence_score": {"type": ["number", "null"]},
            "amount_min": {"type": ["number", "null"]},
            "amount_max": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "billing_unit": {"type": ["string", "null"]},
            "student_type": {"type": ["string", "null"]},
            "degree_level": {"type": ["string", "null"]},
            "academic_year": {"type": ["string", "null"]},
            "date_text": {"type": ["string", "null"]},
            "parsed_date": {"type": ["string", "null"]},
            "round_name": {"type": ["string", "null"]},
            "intake": {"type": ["string", "null"]},
            "test": {"type": ["string", "null"]},
            "overall_score": {"type": ["number", "null"]},
            "min_band": {"type": ["number", "null"]},
            "cert": {"type": ["string", "null"]},
            "requirement_type": {"type": ["string", "null"]},
            "application_system": {"type": ["string", "null"]},
            "rolling_admission": {"type": ["boolean", "null"]},
            "portfolio_required": {"type": ["boolean", "null"]},
            "interview_required": {"type": ["boolean", "null"]},
            "scholarship_available": {"type": ["boolean", "null"]},
            "program_name": {"type": ["string", "null"]},
            "field_of_study": {"type": ["string", "null"]},
        },
        "required": [
            "display_text",
            "supporting_text",
            "confidence_score",
            "amount_min",
            "amount_max",
            "currency",
            "billing_unit",
            "student_type",
            "degree_level",
            "academic_year",
            "date_text",
            "parsed_date",
            "round_name",
            "intake",
            "test",
            "overall_score",
            "min_band",
            "cert",
            "requirement_type",
            "application_system",
            "rolling_admission",
            "portfolio_required",
            "interview_required",
            "scholarship_available",
            "program_name",
            "field_of_study",
        ],
    }
    fact_array = {
        "type": "array",
        "items": item_schema,
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tuition_facts": fact_array,
            "deadline_facts": fact_array,
            "english_requirement_facts": fact_array,
            "cert_requirement_facts": fact_array,
            "application_facts": fact_array,
            "scholarship_facts": fact_array,
            "program_facts": fact_array,
        },
        "required": [
            "tuition_facts",
            "deadline_facts",
            "english_requirement_facts",
            "cert_requirement_facts",
            "application_facts",
            "scholarship_facts",
            "program_facts",
        ],
    }


def llm_response_to_facts(
    evidence: dict[str, str],
    source: dict[str, str],
    response: dict[str, Any],
) -> list[dict[str, object]]:
    text = evidence.get("extracted_text", "")
    source_type = source.get("source_type", "")
    facts: list[dict[str, object]] = []
    if source_type in {"tuition_fees"}:
        for item in safe_list(response.get("tuition_facts")):
            quote = str(item.get("supporting_text", ""))
            if not valid_supporting_text(quote, text):
                continue
            currency = str(item.get("currency") or "USD").upper()
            low = number_or_blank(item.get("amount_min"))
            high = number_or_blank(item.get("amount_max")) or low
            if low == "":
                continue
            facts.append(make_llm_fact(evidence, "tuition", "tuition_fee", item.get("display_text") or quote, {
                "min": low,
                "max": high,
                "currency": currency,
                "billing_unit": item.get("billing_unit", ""),
                "student_type": item.get("student_type", ""),
                "degree_level": item.get("degree_level", ""),
                "academic_year": item.get("academic_year", ""),
                "source_type": source_type,
            }, low, currency, "", quote, item.get("confidence_score", 0.72)))

    if source_type in {"undergraduate_admissions", "graduate_admissions", "international_admissions"}:
        for item in safe_list(response.get("deadline_facts")):
            quote = str(item.get("supporting_text", ""))
            date_text = str(item.get("date_text") or "")
            if not date_text or not valid_supporting_text(quote, text):
                continue
            value_text = item.get("display_text") or f"{item.get('round_name') or 'Deadline'}: {date_text}"
            facts.append(make_llm_fact(evidence, "application", "application_deadline_candidate", value_text, {
                "date_text": date_text,
                "parsed_date": item.get("parsed_date", ""),
                "round_name": item.get("round_name", ""),
                "intake": item.get("intake", ""),
                "degree_level": item.get("degree_level", ""),
                "text": quote,
                "source_type": source_type,
            }, "", "", str(item.get("parsed_date") or ""), quote, item.get("confidence_score", 0.70)))

        for item in safe_list(response.get("application_facts")):
            quote = str(item.get("supporting_text", ""))
            if not valid_supporting_text(quote, text):
                continue
            for key in ["application_system", "rolling_admission", "portfolio_required", "interview_required"]:
                value = item.get(key)
                if value in ("", None, False):
                    continue
                facts.append(make_llm_fact(evidence, "application", key, normalize_bool_text(value), {
                    "source_type": source_type,
                }, "", "", "", quote, item.get("confidence_score", 0.62)))

    if source_type in {"english_requirements", "undergraduate_admissions", "international_admissions"}:
        for item in safe_list(response.get("english_requirement_facts")):
            quote = str(item.get("supporting_text", ""))
            test = normalize_test_name(str(item.get("test") or ""))
            score = number_or_blank(item.get("overall_score"))
            if not test or score == "" or not valid_supporting_text(quote, text):
                continue
            value_text = f"{test} {score:g}" if isinstance(score, float) else f"{test} {score}"
            facts.append(make_llm_fact(evidence, "english_requirement", test, value_text, {
                "test": test,
                "overall": score,
                "min_band": item.get("min_band", ""),
                "degree_level": item.get("degree_level", ""),
            }, score, "", "", quote, item.get("confidence_score", 0.72)))

        for item in safe_list(response.get("cert_requirement_facts")):
            quote = str(item.get("supporting_text", ""))
            cert = normalize_cert_key(str(item.get("cert") or ""))
            if not cert or not valid_supporting_text(quote, text):
                continue
            facts.append(make_llm_fact(evidence, "cert_requirement", cert, cert, {
                "cert": cert,
                "requirement_type": item.get("requirement_type", ""),
                "degree_level": item.get("degree_level", ""),
            }, "", "", "", quote, item.get("confidence_score", 0.65)))

    if source_type in {"scholarships", "undergraduate_admissions", "international_admissions"}:
        for item in safe_list(response.get("scholarship_facts")):
            quote = str(item.get("supporting_text", ""))
            available = item.get("scholarship_available")
            if available is None or not valid_supporting_text(quote, text):
                continue
            facts.append(make_llm_fact(evidence, "scholarship", "scholarship_available", normalize_bool_text(available), {
                "source_type": source_type,
            }, "", "", "", quote, item.get("confidence_score", 0.62)))

    if source_type in {"program_catalog"}:
        for item in safe_list(response.get("program_facts")):
            quote = str(item.get("supporting_text", ""))
            if not valid_supporting_text(quote, text):
                continue
            if item.get("field_of_study"):
                facts.append(make_llm_fact(evidence, "program", "field_of_study", str(item.get("field_of_study")), {
                    "program_name": item.get("program_name", ""),
                    "degree_level": item.get("degree_level", ""),
                }, "", "", "", quote, item.get("confidence_score", 0.58)))
            if item.get("degree_level"):
                facts.append(make_llm_fact(evidence, "program", "degree_level", str(item.get("degree_level")), {
                    "program_name": item.get("program_name", ""),
                    "field_of_study": item.get("field_of_study", ""),
                }, "", "", "", quote, item.get("confidence_score", 0.58)))
    return facts


def make_llm_fact(
    evidence: dict[str, str],
    fact_type: str,
    fact_key: str,
    value_text: object = "",
    value_json: object | None = None,
    value_number: object = "",
    value_currency: str = "",
    value_date: str = "",
    supporting_text: str = "",
    confidence_score: object = 0.65,
) -> dict[str, object]:
    value_json_text = json.dumps(value_json, ensure_ascii=False, sort_keys=True) if value_json is not None else ""
    confidence = clamp_confidence(confidence_score)
    return {
        "fact_id": stable_id("fact", evidence.get("evidence_id"), fact_type, fact_key, str(value_text), value_json_text, "llm"),
        "university_id": evidence.get("university_id", ""),
        "program_id": "",
        "fact_type": fact_type,
        "fact_key": fact_key,
        "value_text": value_text,
        "value_json": value_json_text,
        "value_number": value_number,
        "value_currency": value_currency,
        "value_date": value_date,
        "fact_origin": "llm_extracted_from_source",
        "evidence_id": evidence.get("evidence_id", ""),
        "source_url": evidence.get("url", ""),
        "supporting_text": supporting_text,
        "confidence_score": f"{confidence:.2f}",
        "review_status": "needs_review",
        "extracted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def merge_facts(existing_facts: list[dict[str, object]], llm_facts: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for fact in list(existing_facts) + list(llm_facts):
        key = str(fact.get("fact_id", ""))
        if key and key in seen:
            continue
        merged.append(fact)
        if key:
            seen.add(key)
    merged.sort(key=lambda row: (str(row.get("university_id", "")), str(row.get("fact_type", "")), str(row.get("fact_key", "")), str(row.get("source_url", ""))))
    return merged


def llm_fact_rows(facts: list[dict[str, object]]) -> list[dict[str, object]]:
    return [fact for fact in facts if fact.get("fact_origin") == "llm_extracted_from_source"]


def report_row(evidence: dict[str, str], sources_by_id: dict[str, dict[str, str]], status: str, facts_emitted: int, error: str, model: str) -> dict[str, object]:
    source = sources_by_id.get(evidence.get("source_id", ""), {})
    return {
        "evidence_id": evidence.get("evidence_id", ""),
        "source_id": evidence.get("source_id", ""),
        "university_id": evidence.get("university_id", ""),
        "source_type": source.get("source_type", ""),
        "source_url": evidence.get("url", ""),
        "status": status,
        "facts_emitted": facts_emitted,
        "error": error,
        "model": model,
    }


def write_llm_metadata(out_path: Path, run_id: str, provider: str, model: str, facts_count: int, evidence_count: int) -> None:
    metadata = {
        "run_id": run_id,
        "provider": provider,
        "model": model,
        "prompt_schema_version": LLM_PROMPT_VERSION,
        "facts_llm": facts_count,
        "evidence_rows_seen": evidence_count,
    }
    with (out_path / "llm_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def safe_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def valid_supporting_text(quote: str, text: str) -> bool:
    if not quote or len(quote.strip()) < 8:
        return False
    return normalize_text(quote) in normalize_text(text)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def number_or_blank(value: object) -> float | int | str:
    if value in ("", None):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return int(number) if number.is_integer() else number


def clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.65
    return max(0.0, min(number, 1.0))


def normalize_bool_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    lowered = str(value).strip().lower()
    return "true" if lowered in {"true", "yes", "required", "available"} else str(value).strip()


def normalize_test_name(value: str) -> str:
    lowered = value.strip().lower()
    mapping = {
        "ielts": "IELTS",
        "toefl": "TOEFL",
        "toefl ibt": "TOEFL",
        "pte": "PTE",
        "duolingo": "Duolingo",
        "cambridge english": "Cambridge English",
    }
    return mapping.get(lowered, value.strip())


def normalize_cert_key(value: str) -> str:
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    mapping = {"A_LEVEL": "A_LEVEL", "A_LEVELS": "A_LEVEL"}
    return mapping.get(normalized, normalized)
