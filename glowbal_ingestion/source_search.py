from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .constants import SEARCH_SOURCE_COLUMNS, SOURCE_COLUMNS
from .csv_io import write_csv
from .ids import stable_id

SERPER_ENDPOINT = "https://google.serper.dev/search"

QUERY_TEMPLATES = {
    "undergraduate_admissions": "{name} undergraduate admissions official",
    "tuition_fees": "{name} international tuition fees official",
    "english_requirements": "{name} English language requirements admissions official",
    "program_catalog": "{name} undergraduate programs official",
    "scholarships": "{name} scholarships international students official",
}


def search_source_candidates(
    seed_rows: list[dict[str, str]],
    existing_source_rows: list[dict[str, str]],
    out_path: str | Path,
    source_types: set[str],
    per_type_limit: int = 3,
    api_key: str | None = None,
) -> list[dict[str, object]]:
    key = api_key or os.environ.get("SERPER_API_KEY", "")
    if not key:
        raise RuntimeError("SERPER_API_KEY is required for search-sources")

    existing = {
        (row.get("university_id", ""), row.get("source_type", ""))
        for row in existing_source_rows
    }
    rows: list[dict[str, object]] = []
    for seed in seed_rows:
        for source_type in sorted(source_types):
            if (seed.get("university_id", ""), source_type) in existing:
                continue
            query = QUERY_TEMPLATES.get(source_type, "{name} {source_type} official").format(
                name=seed.get("name", ""),
                source_type=source_type.replace("_", " "),
            )
            results = serper_search(query, key)
            for rank, result in enumerate(results[:per_type_limit], start=1):
                url = str(result.get("link", "")).strip()
                if not url.startswith(("http://", "https://")):
                    continue
                rows.append(
                    {
                        "university_id": seed.get("university_id", ""),
                        "university_name": seed.get("name", ""),
                        "country": seed.get("country", ""),
                        "source_type": source_type,
                        "candidate_url": url,
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "rank": rank,
                        "confidence_score": f"{candidate_confidence(seed, source_type, url, result, rank):.2f}",
                        "search_query": query,
                        "review_status": "needs_review",
                        "crawl_method": "static",
                        "notes": "Serper candidate; review before promotion",
                    }
                )
    rows.sort(key=lambda row: (str(row["university_id"]), str(row["source_type"]), int(row["rank"])))
    write_csv(out_path, rows, SEARCH_SOURCE_COLUMNS)
    return rows


def serper_search(query: str, api_key: str) -> list[dict[str, object]]:
    payload = json.dumps({"q": query, "num": 10}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        SERPER_ENDPOINT,
        data=payload,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Serper search failed for query {query!r}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Serper search failed for query {query!r}: {exc.reason}") from exc
    return list(data.get("organic", []))


def candidate_confidence(seed: dict[str, str], source_type: str, url: str, result: dict[str, object], rank: int) -> float:
    score = 0.45
    host = urllib.parse.urlparse(url).netloc.lower()
    website_host = urllib.parse.urlparse(seed.get("website_url", "")).netloc.lower()
    if website_host and host.endswith(website_host.replace("www.", "")):
        score += 0.25
    joined = f"{result.get('title', '')} {result.get('snippet', '')} {url}".lower()
    for token in source_type.split("_"):
        if token in joined:
            score += 0.05
    if "official" in joined or ".edu" in host or ".ac." in host:
        score += 0.05
    score -= max(rank - 1, 0) * 0.03
    return max(0.05, min(score, 0.95))


def promote_search_sources(
    seed_rows: list[dict[str, str]],
    base_source_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    out_path: str | Path,
) -> list[dict[str, object]]:
    seed_by_id = {row.get("university_id", ""): row for row in seed_rows}
    output: list[dict[str, object]] = [dict(row) for row in base_source_rows]
    existing = {
        (row.get("university_id", ""), row.get("source_type", ""), normalize_url(row.get("url", "")))
        for row in base_source_rows
    }
    for candidate in candidate_rows:
        if candidate.get("review_status", "").lower() != "approved":
            continue
        university_id = candidate.get("university_id", "")
        source_type = candidate.get("source_type", "")
        url = candidate.get("manual_url", "") or candidate.get("candidate_url", "")
        url = normalize_url(url)
        if not university_id or not source_type or not url:
            continue
        key = (university_id, source_type, url)
        if key in existing:
            continue
        seed = seed_by_id.get(university_id, {})
        output.append(
            {
                "source_id": stable_id("src", university_id, source_type, url),
                "university_id": university_id,
                "university_name": seed.get("name", candidate.get("university_name", "")),
                "country": seed.get("country", candidate.get("country", "")),
                "source_type": source_type,
                "url": url,
                "priority": "2",
                "language_code": "",
                "crawl_method": candidate.get("crawl_method", "") or "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": candidate.get("notes", "") or f"promoted from Serper rank {candidate.get('rank', '')}",
            }
        )
        existing.add(key)
    output.sort(
        key=lambda row: (
            str(row.get("university_id", "")),
            int(str(row.get("priority", "9"))) if str(row.get("priority", "9")).isdigit() else 9,
            str(row.get("source_type", "")),
            str(row.get("url", "")),
        )
    )
    write_csv(out_path, output, SOURCE_COLUMNS)
    return output


def normalize_url(url: str) -> str:
    cleaned = re.sub(r"\s+", "", url or "").strip()
    return cleaned.strip("()")
