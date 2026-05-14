from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .crawler import decode_bytes, fetch_bytes
from .constants import SOURCE_COLUMNS
from .csv_io import write_csv
from .ids import stable_id

SUGGESTION_COLUMNS = [
    "university_id",
    "university_name",
    "candidate_source_type",
    "url",
    "anchor_text",
    "confidence_score",
    "reason",
]

TARGET_SOURCE_TYPES = [
    "undergraduate_admissions",
    "international_admissions",
    "graduate_admissions",
    "program_catalog",
    "tuition_fees",
    "scholarships",
    "english_requirements",
    "cost_of_living",
    "housing",
    "career",
]

SOURCE_HINTS = {
    "undergraduate_admissions": [
        "undergraduate admission",
        "undergraduate admissions",
        "apply undergraduate",
        "admissions",
        "apply",
    ],
    "graduate_admissions": [
        "graduate admission",
        "graduate admissions",
        "postgraduate",
        "graduate apply",
    ],
    "international_admissions": [
        "international admissions",
        "international students",
        "international applicants",
    ],
    "program_catalog": [
        "programs",
        "programmes",
        "courses",
        "degrees",
        "academics",
        "study",
    ],
    "tuition_fees": [
        "tuition",
        "fees",
        "cost of attendance",
        "student fees",
    ],
    "scholarships": [
        "scholarship",
        "scholarships",
        "financial aid",
        "bursaries",
        "funding",
    ],
    "english_requirements": [
        "english language",
        "ielts",
        "toefl",
        "language requirements",
        "english requirements",
    ],
    "cost_of_living": [
        "cost of living",
        "living costs",
        "student budget",
    ],
    "housing": [
        "housing",
        "accommodation",
        "residence",
        "residences",
    ],
    "career": [
        "career",
        "careers",
        "employability",
        "internship",
        "co-op",
    ],
}


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_map = dict(attrs)
        self._current_href = attrs_map.get("href") or ""
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._current_href:
            return
        text = normalize_space(" ".join(self._text_parts))
        self.links.append((self._current_href, text))
        self._current_href = ""
        self._text_parts = []


def suggest_sources(source_rows: list[dict[str, str]], out_path: str | Path, timeout: int = 25) -> list[dict[str, object]]:
    suggestions: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()

    for source in source_rows:
        if source.get("source_type") != "official_home":
            continue
        url = source.get("url", "")
        try:
            body, content_type = fetch_bytes(url, timeout)
        except Exception:
            continue
        if "pdf" in content_type.lower():
            continue
        html = decode_bytes(body, content_type)
        parser = LinkExtractor()
        parser.feed(html)
        for href, anchor_text in parser.links:
            absolute_url = clean_url(urljoin(url, href))
            if not should_keep_link(url, absolute_url):
                continue
            for source_type, reason, score in classify_link(absolute_url, anchor_text):
                key = (source.get("university_id", ""), source_type, absolute_url)
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append(
                    {
                        "university_id": source.get("university_id", ""),
                        "university_name": source.get("university_name", ""),
                        "candidate_source_type": source_type,
                        "url": absolute_url,
                        "anchor_text": anchor_text,
                        "confidence_score": f"{score:.2f}",
                        "reason": reason,
                    }
                )

    suggestions.sort(
        key=lambda row: (
            str(row.get("university_id", "")),
            str(row.get("candidate_source_type", "")),
            -float(str(row.get("confidence_score", "0"))),
            str(row.get("url", "")),
        )
    )
    write_csv(out_path, suggestions, SUGGESTION_COLUMNS)
    return suggestions


def build_candidate_source_map(
    current_source_rows: list[dict[str, str]],
    suggestion_rows: list[dict[str, str]],
    out_path: str | Path,
    per_type_limit: int = 1,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    seen_urls_by_university: set[tuple[str, str]] = set()

    for source in current_source_rows:
        row = {
            "source_id": source.get("source_id") or stable_id("src", source.get("university_id"), source.get("source_type"), source.get("url")),
            "university_id": source.get("university_id", ""),
            "university_name": source.get("university_name", ""),
            "country": source.get("country", ""),
            "source_type": source.get("source_type", ""),
            "url": source.get("url", ""),
            "priority": source.get("priority", "1") or "1",
            "language_code": source.get("language_code", ""),
            "crawl_method": source.get("crawl_method", "static") or "static",
            "status": "pending",
            "last_crawled_at": "",
            "notes": source.get("notes", ""),
        }
        key = (str(row["university_id"]), str(row["source_type"]), str(row["url"]))
        url_key = (str(row["university_id"]), str(row["url"]))
        rows.append(row)
        seen_keys.add(key)
        seen_urls_by_university.add(url_key)

    source_meta = {
        source.get("university_id", ""): {
            "university_name": source.get("university_name", ""),
            "country": source.get("country", ""),
            "language_code": source.get("language_code", ""),
        }
        for source in current_source_rows
    }

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for suggestion in suggestion_rows:
        source_type = suggestion.get("candidate_source_type", "")
        if source_type not in TARGET_SOURCE_TYPES:
            continue
        key = (suggestion.get("university_id", ""), source_type)
        grouped.setdefault(key, []).append(suggestion)

    university_ids = sorted({key[0] for key in grouped})
    for university_id in university_ids:
        for source_type in TARGET_SOURCE_TYPES:
            suggestions = grouped.get((university_id, source_type), [])
            if not suggestions:
                continue
            append_candidate_suggestions(
                rows,
                seen_keys,
                seen_urls_by_university,
                source_meta,
                university_id,
                source_type,
                suggestions,
                per_type_limit,
            )

    rows.sort(key=lambda row: (str(row.get("university_id", "")), int(str(row.get("priority", "9"))), str(row.get("source_type", ""))))
    write_csv(out_path, rows, SOURCE_COLUMNS)
    return rows


def append_candidate_suggestions(
    rows: list[dict[str, object]],
    seen_keys: set[tuple[str, str, str]],
    seen_urls_by_university: set[tuple[str, str]],
    source_meta: dict[str, dict[str, str]],
    university_id: str,
    source_type: str,
    suggestions: list[dict[str, str]],
    per_type_limit: int,
) -> None:
        suggestions.sort(
            key=lambda row: (
                -safe_float(row.get("confidence_score", "")),
                len(row.get("url", "")),
                row.get("url", ""),
            )
        )
        selected = 0
        for suggestion in suggestions:
            if selected >= per_type_limit:
                break
            url = suggestion.get("url", "")
            key = (university_id, source_type, url)
            url_key = (university_id, url)
            if key in seen_keys or url_key in seen_urls_by_university:
                continue
            meta = source_meta.get(university_id, {})
            rows.append(
                {
                    "source_id": stable_id("src", university_id, source_type, url),
                    "university_id": university_id,
                    "university_name": meta.get("university_name", suggestion.get("university_name", "")),
                    "country": meta.get("country", ""),
                    "source_type": source_type,
                    "url": url,
                    "priority": "2",
                    "language_code": meta.get("language_code", ""),
                    "crawl_method": "static",
                    "status": "pending",
                    "last_crawled_at": "",
                    "notes": f"candidate from homepage link; review before promotion; {suggestion.get('reason', '')}",
                }
            )
            seen_keys.add(key)
            seen_urls_by_university.add(url_key)
            selected += 1


def classify_link(url: str, anchor_text: str) -> list[tuple[str, str, float]]:
    haystack = f"{anchor_text} {url}".lower().replace("-", " ").replace("_", " ")
    matches: list[tuple[str, str, float]] = []
    for source_type, hints in SOURCE_HINTS.items():
        best_hint = ""
        for hint in hints:
            if hint in haystack:
                best_hint = hint
                break
        if best_hint:
            score = 0.75 if best_hint in anchor_text.lower() else 0.55
            matches.append((source_type, f"matched keyword '{best_hint}'", score))
    return matches


def should_keep_link(base_url: str, candidate_url: str) -> bool:
    parsed = urlparse(candidate_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.fragment:
        candidate_url = candidate_url.split("#", 1)[0]
    if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|zip|mp4|mp3)$", parsed.path, flags=re.I):
        return False
    if urlparse(base_url).scheme == "file":
        return True
    base_domain = comparable_domain(urlparse(base_url).netloc)
    candidate_domain = comparable_domain(parsed.netloc)
    return candidate_domain == base_domain or candidate_domain.endswith(f".{base_domain}")


def comparable_domain(netloc: str) -> str:
    host = netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in {"ac.uk", "edu.au", "edu.cn"}:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def clean_url(url: str) -> str:
    return url.split("#", 1)[0]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def safe_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
