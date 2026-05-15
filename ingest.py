from __future__ import annotations

import argparse
import sys
from pathlib import Path

from glowbal_ingestion.crawler import crawl_sources
from glowbal_ingestion.csv_io import read_csv
from glowbal_ingestion.discovery import build_candidate_source_map, suggest_sources
from glowbal_ingestion.extractors import extract_facts
from glowbal_ingestion.manifest import default_run_id, write_run_manifest
from glowbal_ingestion.profiles import build_profiles
from glowbal_ingestion.quality import classify_evidence_rows
from glowbal_ingestion.source_map_tools import apply_source_repairs, build_retry_source_map, merge_crawl_outputs, normalize_source_map
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
    profile_parser.add_argument("--country-costs", default="")
    profile_parser.add_argument("--evidence", default="")
    profile_parser.add_argument("--run-id", default="")

    run_parser = subparsers.add_parser("run-pilot", help="Run validate, crawl, extract, and profile stages")
    run_parser.add_argument("--seed", required=True)
    run_parser.add_argument("--sources", required=True)
    run_parser.add_argument("--rankings", required=True)
    run_parser.add_argument("--out-dir", required=True)
    run_parser.add_argument("--timeout", type=int, default=25)
    run_parser.add_argument("--country-costs", default="")
    run_parser.add_argument("--run-id", default="")

    discover_parser = subparsers.add_parser("discover-sources", help="Create a minimal source-map starter from seed rows")
    discover_parser.add_argument("--seed", required=True)
    discover_parser.add_argument("--out", required=True)

    suggest_parser = subparsers.add_parser("suggest-sources", help="Suggest candidate source URLs from official homepage links")
    suggest_parser.add_argument("--sources", required=True)
    suggest_parser.add_argument("--out", required=True)
    suggest_parser.add_argument("--timeout", type=int, default=25)

    candidate_parser = subparsers.add_parser("build-source-map-candidates", help="Build a reviewable source map from suggestions")
    candidate_parser.add_argument("--sources", required=True)
    candidate_parser.add_argument("--suggestions", required=True)
    candidate_parser.add_argument("--out", required=True)
    candidate_parser.add_argument("--per-type-limit", type=int, default=1)

    normalize_parser = subparsers.add_parser("normalize-source-map", help="Normalize source-map IDs and remove invalid rows")
    normalize_parser.add_argument("--seed", required=True)
    normalize_parser.add_argument("--sources", required=True)
    normalize_parser.add_argument("--out", required=True)

    retry_parser = subparsers.add_parser("build-retry-source-map", help="Build a retry source map from failed/skipped source rows")
    retry_parser.add_argument("--sources", required=True)
    retry_parser.add_argument("--out", required=True)
    retry_parser.add_argument("--source-types", default="")

    merge_parser = subparsers.add_parser("merge-crawl-outputs", help="Merge successful retry crawl rows into a base crawl output")
    merge_parser.add_argument("--base-sources", required=True)
    merge_parser.add_argument("--base-evidence", required=True)
    merge_parser.add_argument("--retry-sources", required=True)
    merge_parser.add_argument("--retry-evidence", required=True)
    merge_parser.add_argument("--out-dir", required=True)

    repair_parser = subparsers.add_parser("apply-source-repairs", help="Apply source_repair_resolved.csv into a full source map")
    repair_parser.add_argument("--seed", required=True)
    repair_parser.add_argument("--base-sources", required=True)
    repair_parser.add_argument("--repairs", required=True)
    repair_parser.add_argument("--out", required=True)

    classify_parser = subparsers.add_parser("classify-evidence", help="Backfill evidence content quality columns")
    classify_parser.add_argument("--sources", required=True)
    classify_parser.add_argument("--evidence", required=True)
    classify_parser.add_argument("--out", required=True)

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
            read_optional_csv(args.country_costs),
            read_optional_csv(args.evidence),
        )
        write_profile_manifest(args.out_dir, args.run_id, args.seed, args.sources, args.facts, args.rankings, args.country_costs, args.evidence)
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
            read_optional_csv(args.country_costs),
            read_csv(out_dir / "evidence.csv"),
        )
        write_pipeline_manifest(args.out_dir, args.run_id, args.seed, args.sources, args.rankings, args.country_costs)
        print(f"Pilot pipeline complete: {out_dir}")
        return 0
    if args.command == "discover-sources":
        return command_discover(args.seed, args.out)
    if args.command == "suggest-sources":
        suggestions = suggest_sources(read_csv(args.sources), args.out, timeout=args.timeout)
        print(f"Wrote {len(suggestions)} source suggestions to {args.out}")
        return 0
    if args.command == "build-source-map-candidates":
        rows = build_candidate_source_map(
            read_csv(args.sources),
            read_csv(args.suggestions),
            args.out,
            per_type_limit=args.per_type_limit,
        )
        print(f"Wrote {len(rows)} candidate source-map rows to {args.out}")
        return 0
    if args.command == "normalize-source-map":
        stats = normalize_source_map(
            read_csv(args.seed),
            read_csv(args.sources),
            args.out,
            backup_input_path=args.sources,
        )
        for key, value in stats.items():
            print(f"{key}: {value}")
        return 0
    if args.command == "build-retry-source-map":
        source_types = {part.strip() for part in args.source_types.split(",") if part.strip()} or None
        rows = build_retry_source_map(read_csv(args.sources), args.out, source_types=source_types)
        print(f"Wrote {len(rows)} retry source rows to {args.out}")
        return 0
    if args.command == "merge-crawl-outputs":
        stats = merge_crawl_outputs(
            read_csv(args.base_sources),
            read_csv(args.base_evidence),
            read_csv(args.retry_sources),
            read_csv(args.retry_evidence),
            args.out_dir,
        )
        for key, value in stats.items():
            print(f"{key}: {value}")
        return 0
    if args.command == "apply-source-repairs":
        stats = apply_source_repairs(
            read_csv(args.seed),
            read_csv(args.base_sources),
            read_csv(args.repairs),
            args.out,
        )
        for key, value in stats.items():
            print(f"{key}: {value}")
        return 0
    if args.command == "classify-evidence":
        from glowbal_ingestion.constants import EVIDENCE_COLUMNS
        from glowbal_ingestion.csv_io import write_csv

        rows = classify_evidence_rows(read_csv(args.sources), read_csv(args.evidence))
        write_csv(args.out, rows, EVIDENCE_COLUMNS)
        print(f"Wrote {len(rows)} classified evidence rows to {args.out}")
        return 0

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


def read_optional_csv(path: str) -> list[dict[str, str]]:
    return read_csv(path) if path else []


def write_profile_manifest(
    out_dir: str,
    run_id: str,
    seed: str,
    sources: str,
    facts: str,
    rankings: str,
    country_costs: str,
    evidence: str,
) -> None:
    output_dir = Path(out_dir)
    write_run_manifest(
        output_dir,
        run_id or default_run_id("profiles"),
        {
            "seed": seed,
            "sources": sources,
            "evidence": evidence,
            "facts": facts,
            "rankings": rankings,
            "country_costs": country_costs,
        },
        {
            "sources": sources,
            "evidence": evidence,
            "facts": facts,
            "facts_extracted": str(output_dir / "facts_extracted.csv"),
            "facts_generated": str(output_dir / "facts_generated.csv"),
            "programs": str(output_dir / "programs.csv"),
            "product_profiles": str(output_dir / "university_product_profiles.csv"),
            "import": str(output_dir / "universities_import.csv"),
            "matching_tags": str(output_dir / "university_matching_tags.csv"),
            "writer_context": str(output_dir / "university_writer_context.csv"),
            "qa_report": str(output_dir / "qa_report.csv"),
            "batch_qa_report": str(output_dir / "batch_qa_report.csv"),
            "field_gap_report": str(output_dir / "field_gap_report.csv"),
            "quality_gate": str(output_dir / "pilot_quality_gate.csv"),
        },
    )


def write_pipeline_manifest(
    out_dir: str,
    run_id: str,
    seed: str,
    sources: str,
    rankings: str,
    country_costs: str,
) -> None:
    output_dir = Path(out_dir)
    write_run_manifest(
        output_dir,
        run_id or default_run_id("pilot"),
        {
            "seed": seed,
            "sources": sources,
            "rankings": rankings,
            "country_costs": country_costs,
        },
        {
            "sources": str(output_dir / "sources.csv"),
            "evidence": str(output_dir / "evidence.csv"),
            "facts": str(output_dir / "facts.csv"),
            "facts_extracted": str(output_dir / "facts_extracted.csv"),
            "facts_generated": str(output_dir / "facts_generated.csv"),
            "programs": str(output_dir / "programs.csv"),
            "product_profiles": str(output_dir / "university_product_profiles.csv"),
            "import": str(output_dir / "universities_import.csv"),
            "matching_tags": str(output_dir / "university_matching_tags.csv"),
            "writer_context": str(output_dir / "university_writer_context.csv"),
            "qa_report": str(output_dir / "qa_report.csv"),
            "batch_qa_report": str(output_dir / "batch_qa_report.csv"),
            "field_gap_report": str(output_dir / "field_gap_report.csv"),
            "quality_gate": str(output_dir / "pilot_quality_gate.csv"),
        },
    )


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
