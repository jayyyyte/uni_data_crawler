from __future__ import annotations

import re

SOURCE_TYPE_KEYWORDS = {
    "official_home": ["university", "campus", "students", "research", "admissions"],
    "undergraduate_admissions": ["apply", "admission", "undergraduate", "deadline", "requirements"],
    "graduate_admissions": ["graduate", "postgraduate", "admission", "apply", "requirements"],
    "international_admissions": ["international", "admission", "applicants", "requirements"],
    "program_catalog": ["program", "programme", "course", "degree", "bachelor", "master"],
    "tuition_fees": ["tuition", "fee", "fees", "cost", "international student"],
    "scholarships": ["scholarship", "financial aid", "bursary", "funding", "grant"],
    "english_requirements": ["english", "ielts", "toefl", "pte", "duolingo", "language"],
    "cost_of_living": ["living cost", "cost of living", "accommodation", "housing", "expenses"],
    "housing": ["housing", "accommodation", "residence", "residences"],
    "career": ["career", "employability", "internship", "placement"],
}

BLOCKED_PATTERNS = [
    ("blocked", ["403 forbidden", "access denied", "request unsuccessful. incapsula incident id"]),
    ("js_challenge", ["just a moment", "enable javascript", "verify you are human", "checking your browser"]),
    ("not_found", ["404 not found", "page not found", "oops! page not found", "the page you requested could not be found"]),
]


def classify_evidence_quality(source_type: str, title: str, text: str, fetch_status: str, error: str = "") -> dict[str, object]:
    text = text or ""
    joined = f"{title or ''} {text}".lower()
    text_len = len(text)

    if fetch_status == "failed":
        return result("fetch_failed", error or "fetch failed", text_len, 0.0)

    for status, patterns in BLOCKED_PATTERNS:
        if any(pattern in joined for pattern in patterns):
            return result(status, f"matched {status} pattern", text_len, 0.0)

    if text_len < 120:
        return result("too_short", "text_len < 120", text_len, 0.0)
    if text_len < 800:
        return result("too_short", "text_len < 800", text_len, 0.15)

    signal_score = source_signal_score(source_type, joined)
    if signal_score <= 0:
        return result("low_signal", f"missing expected keywords for {source_type}", text_len, 0.2)

    return result("usable", "passed basic content checks", text_len, signal_score)


def result(status: str, reason: str, text_len: int, score: float) -> dict[str, object]:
    return {
        "content_quality_status": status,
        "content_quality_reason": reason,
        "text_len": text_len,
        "content_signal_score": f"{score:.2f}",
    }


def source_signal_score(source_type: str, lowered_text: str) -> float:
    keywords = SOURCE_TYPE_KEYWORDS.get(source_type, [])
    if not keywords:
        return 0.5
    matches = sum(1 for keyword in keywords if keyword in lowered_text)
    return min(1.0, matches / max(2, len(keywords)))


def classify_evidence_rows(
    source_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    sources_by_id = {row.get("source_id", ""): row for row in source_rows}
    output: list[dict[str, object]] = []
    for evidence in evidence_rows:
        source = sources_by_id.get(evidence.get("source_id", ""), {})
        fetch_status = evidence.get("fetch_status") or ("fetched" if evidence.get("status") == "ok" else "failed")
        row = dict(evidence)
        row["fetch_status"] = fetch_status
        row.update(
            classify_evidence_quality(
                source.get("source_type", ""),
                evidence.get("title", ""),
                evidence.get("extracted_text", ""),
                fetch_status,
                evidence.get("error", ""),
            )
        )
        output.append(row)
    return output
