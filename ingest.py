from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glowbal_ingestion.crawler import crawl_sources
from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.extractors import extract_facts
from glowbal_ingestion.profiles import build_profiles
from glowbal_ingestion.validation import validate_seed_rows, validate_source_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Glowbal university ingestion pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-sources", help="Validate seed and source map CSVs")
    validate_parser.add_argument("--seed", required=True)
    validate_parser.add_argument("--sources", required=True)

    crawl_parser = subparsers.add_parser("crawl-sources", help="Crawl approved source map URLs")
    crawl_parser.add_argument("--sources", required=True)
    crawl_parser.add_argument("--out-dir", required=True)
    crawl_parser.add_argument("--timeout", type=int, default=25)

    extract_parser = subparsers.add_parser("extract-facts", help="Extract evidence-backed facts")
    extract_parser.add_argument("--sources", required=True)
    extract_parser.add_argument("--evidence", required=True)
    extract_parser.add_argument("--out-dir", required=True)

    profile_parser = subparsers.add_parser("build-profiles", help="Build product profiles and QA report")
    profile_parser.add_argument("--seed", required=True)
    profile_parser.add_argument("--sources", required=True)
    profile_parser.add_argument("--facts", required=True)
    profile_parser.add_argument("--rankings", required=True)
    profile_parser.add_argument("--out-dir", required=True)

    run_parser = subparsers.add_parser("run-pilot", help="Run validate, crawl, extract, and profile stages")
    run_parser.add_argument("--seed", required=True)
    run_parser.add_argument("--sources", required=True)
    run_parser.add_argument("--rankings", required=True)
    run_parser.add_argument("--out-dir", required=True)
    run_parser.add_argument("--timeout", type=int, default=25)

    discover_parser = subparsers.add_parser("discover-sources", help="Create a minimal source-map starter from seed rows")
    discover_parser.add_argument("--seed", required=True)
    discover_parser.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.command == "validate-sources":
        return command_validate(args.seed, args.sources)
    if args.command == "crawl-sources":
        source_rows = read_csv(args.sources)
        crawl_sources(source_rows, args.out_dir, timeout=args.timeout)
        print(f"Wrote crawl outputs to {args.out_dir}")
        return 0
    if args.command == "extract-facts":
        source_rows = read_csv(args.sources)
        evidence_rows = read_csv(args.evidence)
        extract_facts(source_rows, evidence_rows, args.out_dir)
        print(f"Wrote facts.csv and programs.csv to {args.out_dir}")
        return 0
    if args.command == "build-profiles":
        build_profiles(
            read_csv(args.seed),
            read_csv(args.sources),
            read_csv(args.facts),
            read_csv(args.rankings),
            args.out_dir,
        )
        print(f"Wrote product and QA exports to {args.out_dir}")
        return 0
    if args.command == "run-pilot":
        validation_code = command_validate(args.seed, args.sources)
        if validation_code != 0:
            return validation_code
        out_dir = Path(args.out_dir)
        crawl_sources(read_csv(args.sources), out_dir, timeout=args.timeout)
        extract_facts(read_csv(out_dir / "sources.csv"), read_csv(out_dir / "evidence.csv"), out_dir)
        build_profiles(
            read_csv(args.seed),
            read_csv(out_dir / "sources.csv"),
            read_csv(out_dir / "facts.csv"),
            read_csv(args.rankings),
            out_dir,
        )
        print(f"Pilot pipeline complete: {out_dir}")
        return 0
    if args.command == "discover-sources":
        return command_discover(args.seed, args.out)

    parser.error(f"Unsupported command: {args.command}")
    return 2


def command_validate(seed_path: str, sources_path: str) -> int:
    seed_rows = read_csv(seed_path)
    source_rows = read_csv(sources_path)
    errors = validate_seed_rows(seed_rows) + validate_source_rows(source_rows, seed_rows)
    if errors:
        print("Validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Validation passed")
    return 0


def command_discover(seed_path: str, out_path: str) -> int:
    from glowbal_ingestion.constants import SOURCE_COLUMNS
    from glowbal_ingestion.csv_io import write_csv
    from glowbal_ingestion.ids import stable_id

    rows = []
    for seed in read_csv(seed_path):
        url = seed.get("website_url", "")
        rows.append(
            {
                "source_id": stable_id("src", seed.get("university_id"), "official_home", url),
                "university_id": seed.get("university_id", ""),
                "university_name": seed.get("name", ""),
                "country": seed.get("country", ""),
                "source_type": "official_home",
                "url": url,
                "priority": "1",
                "language_code": "",
                "crawl_method": "static",
                "status": "pending",
                "last_crawled_at": "",
                "notes": "starter source generated from seed website_url; curate before crawling",
            }
        )
    write_csv(out_path, rows, SOURCE_COLUMNS)
    print(f"Wrote starter source map to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

