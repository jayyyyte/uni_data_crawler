from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .constants import PARSER_VERSION


def write_run_manifest(
    out_dir: str | Path,
    run_id: str,
    input_files: dict[str, str],
    output_files: dict[str, str],
) -> dict[str, object]:
    output_path = Path(out_dir)
    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pipeline_version": PARSER_VERSION,
        "git_commit": git_commit(),
        "input_files": input_files,
        "output_files": output_files,
        "row_counts": {name: count_csv_rows(path) for name, path in output_files.items() if path.endswith(".csv")},
        "quality_gate_summary": read_quality_gate(output_path / "pilot_quality_gate.csv"),
    }
    with (output_path / "run_manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def default_run_id(prefix: str = "pilot_validated") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}"


def count_csv_rows(path: str | Path) -> int:
    csv_path = Path(path)
    if not csv_path.exists():
        return 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for row in csv.DictReader(handle) if any((value or "").strip() for value in row.values()))


def read_quality_gate(path: str | Path) -> list[dict[str, str]]:
    gate_path = Path(path)
    if not gate_path.exists():
        return []
    with gate_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()
