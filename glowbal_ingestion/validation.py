from __future__ import annotations

from urllib.parse import urlparse

from .constants import CRAWL_METHODS, SEED_COLUMNS, SOURCE_TYPES

REQUIRED_SEED_COLUMNS = ["university_id", "name", "country", "city", "website_url", "type"]
REQUIRED_SOURCE_COLUMNS = ["university_id", "university_name", "country", "source_type", "url"]


def validate_seed_rows(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if not rows:
        errors.append("seed CSV has no data rows")
        return errors

    present = set(rows[0])
    for column in REQUIRED_SEED_COLUMNS:
        if column not in present:
            errors.append(f"seed CSV missing required column: {column}")

    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        university_id = row.get("university_id", "")
        if not university_id:
            errors.append(f"seed row {index}: missing university_id")
        elif university_id in seen_ids:
            errors.append(f"seed row {index}: duplicate university_id {university_id}")
        seen_ids.add(university_id)

        website_url = row.get("website_url", "")
        if website_url and not is_valid_source_url(website_url):
            errors.append(f"seed row {index}: invalid website_url {website_url}")

    extra_columns = present - set(SEED_COLUMNS)
    for column in sorted(extra_columns):
        errors.append(f"seed CSV has unsupported column: {column}")
    return errors


def validate_source_rows(rows: list[dict[str, str]], seed_rows: list[dict[str, str]] | None = None) -> list[str]:
    errors: list[str] = []
    if not rows:
        errors.append("source map CSV has no data rows")
        return errors

    present = set(rows[0])
    for column in REQUIRED_SOURCE_COLUMNS:
        if column not in present:
            errors.append(f"source map missing required column: {column}")

    seed_ids = {row.get("university_id", "") for row in seed_rows or []}
    seen_source_keys: set[tuple[str, str, str]] = set()
    seen_urls_by_university: set[tuple[str, str]] = set()

    for index, row in enumerate(rows, start=2):
        university_id = row.get("university_id", "")
        source_type = row.get("source_type", "")
        url = row.get("url", "")
        crawl_method = row.get("crawl_method", "") or "static"

        if not university_id:
            errors.append(f"source row {index}: missing university_id")
        elif seed_ids and university_id not in seed_ids:
            errors.append(f"source row {index}: university_id {university_id} not present in seed")

        if source_type not in SOURCE_TYPES:
            errors.append(f"source row {index}: unsupported source_type {source_type}")

        if crawl_method not in CRAWL_METHODS:
            errors.append(f"source row {index}: unsupported crawl_method {crawl_method}")

        if not is_valid_source_url(url):
            errors.append(f"source row {index}: invalid url {url}")

        source_key = (university_id, source_type, url)
        if source_key in seen_source_keys:
            errors.append(f"source row {index}: duplicate source for {university_id} {source_type} {url}")
        seen_source_keys.add(source_key)

        url_key = (university_id, url)
        if url_key in seen_urls_by_university:
            errors.append(f"source row {index}: duplicate URL for {university_id}: {url}")
        seen_urls_by_university.add(url_key)

        priority = row.get("priority", "")
        if priority:
            try:
                if int(priority) < 1:
                    errors.append(f"source row {index}: priority must be >= 1")
            except ValueError:
                errors.append(f"source row {index}: priority must be an integer")

    return errors


def is_valid_source_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if parsed.scheme == "file":
        return bool(parsed.path)
    return False

