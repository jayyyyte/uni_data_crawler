from __future__ import annotations

import shutil
from pathlib import Path

from .constants import SOURCE_COLUMNS
from .constants import EVIDENCE_COLUMNS
from .csv_io import write_csv
from .ids import stable_id
from .validation import is_valid_source_url

UNIVERSITY_ID_ALIASES = {
    "uva_nl": "amsterdam",
    "anu_au": "anu",
    "auck_nz": "auckland",
    "bocconi_it": "bocconi",
    "caltech_us": "caltech",
    "cam_uk": "cambridge",
    "cmu_us": "cmu",
    "columbia_us": "columbia",
    "cornell_us": "cornell",
    "cuhk_hk": "cuhk",
    "tudelft_nl": "delft",
    "ed_uk": "edinburgh",
    "epfl_ch": "epfl",
    "ethz_ch": "eth-zurich",
    "harvard_us": "harvard",
    "heidelberg_de": "heidelberg",
    "hku_hk": "hku",
    "hkust_hk": "hkust",
    "imperial_uk": "imperial",
    "kaist_kr": "kaist",
    "kcl_uk": "kcl",
    "kuleuven_be": "ku-leuven",
    "kyoto_jp": "kyoto",
    "lmu_de": "lmu-munich",
    "melb_au": "melbourne",
    "mit_us": "mit",
    "nus_sg": "nus",
    "oxford_uk": "oxford",
    "pku_cn": "peking",
    "princeton_us": "princeton",
    "snu_kr": "snu",
    "sorbonne_fr": "sorbonne",
    "stanford_us": "stanford",
    "usyd_au": "sydney",
    "utokyo_jp": "tokyo",
    "utoronto_ca": "toronto",
    "tsinghua_cn": "tsinghua",
    "ubc_ca": "ubc",
    "uchicago_us": "uchicago",
    "ucl_uk": "ucl",
    "yale_us": "yale",
}


def normalize_source_map(
    seed_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    output_path: str | Path,
    backup_input_path: str | Path | None = None,
) -> dict[str, int]:
    seed_by_id = {row.get("university_id", ""): row for row in seed_rows}
    normalized_rows: list[dict[str, object]] = []
    seen_exact_sources: set[tuple[str, str, str]] = set()
    stats = {
        "input_rows": len(source_rows),
        "output_rows": 0,
        "mapped_university_ids": 0,
        "removed_blank_rows": 0,
        "removed_invalid_url_rows": 0,
        "removed_exact_duplicates": 0,
    }

    for row in source_rows:
        if is_blank_row(row):
            stats["removed_blank_rows"] += 1
            continue

        original_university_id = row.get("university_id", "")
        university_id = UNIVERSITY_ID_ALIASES.get(original_university_id, original_university_id)
        if university_id != original_university_id:
            stats["mapped_university_ids"] += 1

        url = row.get("url", "")
        if not is_valid_source_url(url):
            stats["removed_invalid_url_rows"] += 1
            continue

        source_type = row.get("source_type", "")
        exact_key = (university_id, source_type, url)
        if exact_key in seen_exact_sources:
            stats["removed_exact_duplicates"] += 1
            continue
        seen_exact_sources.add(exact_key)

        seed = seed_by_id.get(university_id, {})
        crawl_method = row.get("crawl_method", "") or "static"
        normalized_rows.append(
            {
                "source_id": row.get("source_id", "") or stable_id("src", university_id, source_type, url),
                "university_id": university_id,
                "university_name": seed.get("name") or row.get("university_name", ""),
                "country": seed.get("country") or row.get("country", ""),
                "source_type": source_type,
                "url": url,
                "priority": row.get("priority", "") or "2",
                "language_code": row.get("language_code", "") or "en",
                "crawl_method": crawl_method,
                "status": row.get("status", "") or "pending",
                "last_crawled_at": row.get("last_crawled_at", ""),
                "notes": row.get("notes", ""),
            }
        )

    normalized_rows.sort(
        key=lambda item: (
            str(item["university_id"]),
            int(str(item["priority"])) if str(item["priority"]).isdigit() else 9,
            str(item["source_type"]),
            str(item["url"]),
        )
    )

    out = Path(output_path)
    if backup_input_path is not None and Path(backup_input_path).resolve() == out.resolve() and out.exists():
        backup_path = out.with_suffix(out.suffix + ".bak")
        shutil.copy2(out, backup_path)

    write_csv(out, normalized_rows, SOURCE_COLUMNS)
    stats["output_rows"] = len(normalized_rows)
    return stats


def is_blank_row(row: dict[str, str]) -> bool:
    return not any(value.strip() for value in row.values())


def build_retry_source_map(
    source_rows: list[dict[str, str]],
    output_path: str | Path,
    statuses: set[str] | None = None,
    source_types: set[str] | None = None,
) -> list[dict[str, object]]:
    retry_statuses = statuses or {"failed", "skipped"}
    rows: list[dict[str, object]] = []
    for source in source_rows:
        if source.get("status", "") not in retry_statuses:
            continue
        if source_types is not None and source.get("source_type", "") not in source_types:
            continue
        rows.append(
            {
                "source_id": source.get("source_id", ""),
                "university_id": source.get("university_id", ""),
                "university_name": source.get("university_name", ""),
                "country": source.get("country", ""),
                "source_type": source.get("source_type", ""),
                "url": source.get("url", ""),
                "priority": source.get("priority", "2") or "2",
                "language_code": source.get("language_code", "en") or "en",
                "crawl_method": source.get("crawl_method", "static") or "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": source.get("notes", ""),
            }
        )
    rows.sort(key=lambda item: (str(item["university_id"]), str(item["source_type"]), str(item["url"])))
    write_csv(output_path, rows, SOURCE_COLUMNS)
    return rows


def apply_source_repairs(
    seed_rows: list[dict[str, str]],
    base_source_rows: list[dict[str, str]],
    repair_rows: list[dict[str, str]],
    output_path: str | Path,
) -> dict[str, int]:
    seed_by_id = {row.get("university_id", ""): row for row in seed_rows}
    base_by_key = {
        (row.get("university_id", ""), row.get("source_type", "")): row
        for row in base_source_rows
    }
    repair_by_key = {
        (row.get("university_id", ""), row.get("source_type", "")): row
        for row in repair_rows
        if row.get("university_id") and row.get("source_type") and row.get("url")
    }
    output_rows: list[dict[str, object]] = []
    used_repairs: set[tuple[str, str]] = set()
    stats = {
        "base_rows": len(base_source_rows),
        "repair_rows": len(repair_rows),
        "updated_rows": 0,
        "added_rows": 0,
        "output_rows": 0,
    }

    for base in base_source_rows:
        key = (base.get("university_id", ""), base.get("source_type", ""))
        repair = repair_by_key.get(key) if key not in used_repairs else None
        if repair:
            output_rows.append(source_row_from_repair(seed_by_id, base, repair))
            used_repairs.add(key)
            stats["updated_rows"] += 1
        else:
            output_rows.append(reset_source_status(base))

    for key, repair in repair_by_key.items():
        if key in used_repairs:
            continue
        university_id, source_type = key
        seed = seed_by_id.get(university_id, {})
        url = repair.get("url", "")
        output_rows.append(
            {
                "source_id": stable_id("src", university_id, source_type, url),
                "university_id": university_id,
                "university_name": seed.get("name", ""),
                "country": seed.get("country", ""),
                "source_type": source_type,
                "url": url,
                "priority": "2",
                "language_code": "en",
                "crawl_method": repair.get("crawl_method", "") or "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": repair.get("notes", ""),
            }
        )
        stats["added_rows"] += 1

    output_rows.sort(
        key=lambda item: (
            str(item["university_id"]),
            int(str(item["priority"])) if str(item["priority"]).isdigit() else 9,
            str(item["source_type"]),
            str(item["url"]),
        )
    )
    write_csv(output_path, output_rows, SOURCE_COLUMNS)
    stats["output_rows"] = len(output_rows)
    return stats


def source_row_from_repair(
    seed_by_id: dict[str, dict[str, str]],
    base: dict[str, str],
    repair: dict[str, str],
) -> dict[str, object]:
    university_id = repair.get("university_id", "") or base.get("university_id", "")
    source_type = repair.get("source_type", "") or base.get("source_type", "")
    url = repair.get("url", "") or base.get("url", "")
    seed = seed_by_id.get(university_id, {})
    return {
        "source_id": base.get("source_id") or stable_id("src", university_id, source_type, url),
        "university_id": university_id,
        "university_name": seed.get("name") or base.get("university_name", ""),
        "country": seed.get("country") or base.get("country", ""),
        "source_type": source_type,
        "url": url,
        "priority": base.get("priority", "") or "2",
        "language_code": base.get("language_code", "") or "en",
        "crawl_method": repair.get("crawl_method", "") or base.get("crawl_method", "") or "static",
        "status": "pending",
        "last_crawled_at": "",
        "notes": repair.get("notes", "") or base.get("notes", ""),
    }


def reset_source_status(row: dict[str, str]) -> dict[str, object]:
    output = dict(row)
    output["status"] = "pending"
    output["last_crawled_at"] = ""
    return output


def merge_crawl_outputs(
    base_sources: list[dict[str, str]],
    base_evidence: list[dict[str, str]],
    retry_sources: list[dict[str, str]],
    retry_evidence: list[dict[str, str]],
    out_dir: str | Path,
) -> dict[str, int]:
    retry_sources_by_id = {row.get("source_id", ""): row for row in retry_sources}
    retry_evidence_by_source_id = {row.get("source_id", ""): row for row in retry_evidence}
    merged_sources: list[dict[str, object]] = []
    merged_evidence: list[dict[str, object]] = []
    stats = {
        "base_sources": len(base_sources),
        "base_evidence": len(base_evidence),
        "retry_sources": len(retry_sources),
        "retry_evidence": len(retry_evidence),
        "sources_replaced": 0,
        "evidence_replaced": 0,
    }

    for source in base_sources:
        source_id = source.get("source_id", "")
        retry_source = retry_sources_by_id.get(source_id)
        if retry_source and should_replace_crawl_row(source.get("status", ""), retry_source.get("status", "")):
            merged_sources.append(retry_source)
            stats["sources_replaced"] += 1
        else:
            merged_sources.append(source)

    for evidence in base_evidence:
        source_id = evidence.get("source_id", "")
        retry_evidence = retry_evidence_by_source_id.get(source_id)
        if retry_evidence and should_replace_evidence_row(evidence.get("status", ""), retry_evidence.get("status", "")):
            merged_evidence.append(retry_evidence)
            stats["evidence_replaced"] += 1
        else:
            merged_evidence.append(evidence)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    write_csv(out_path / "sources.csv", merged_sources, SOURCE_COLUMNS)
    write_csv(out_path / "evidence.csv", merged_evidence, EVIDENCE_COLUMNS)
    return stats


def should_replace_crawl_row(base_status: str, retry_status: str) -> bool:
    if retry_status == "fetched":
        return True
    return base_status != "fetched" and retry_status in {"failed", "skipped"}


def should_replace_evidence_row(base_status: str, retry_status: str) -> bool:
    if retry_status == "ok":
        return True
    return base_status != "ok" and retry_status in {"failed", "empty", "playwright_required"}
