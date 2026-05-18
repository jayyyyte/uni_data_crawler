from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Iterable

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def read_csv(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        delimiter = "\t" if sample.splitlines() and sample.splitlines()[0].count("\t") > sample.splitlines()[0].count(",") else ","
        return [row for row in (normalize_row(row) for row in csv.DictReader(handle, delimiter=delimiter)) if any(row.values())]


def write_csv(path: str | Path, rows: Iterable[dict[str, object]], columns: list[str]) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: encode_cell(row.get(column, "")) for column in columns})


def normalize_row(row: dict[str, str | None]) -> dict[str, str]:
    return {key: (value or "").strip() for key, value in row.items() if key is not None}


def encode_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def parse_json_cell(value: str) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
