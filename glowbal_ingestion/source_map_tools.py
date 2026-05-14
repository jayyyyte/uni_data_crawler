from __future__ import annotations

import shutil
from pathlib import Path

from .constants import SOURCE_COLUMNS
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
