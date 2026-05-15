# Glowbal University Data Ingestion

Evidence-first ingestion pipeline for Glowbal university data. The first phase is built to validate a pilot batch of 50 universities, export QA/product CSVs, and keep the existing app-facing `universities` table untouched until the data is approved.

## What This Pipeline Does

1. Reads a curated `seed_universities_50.csv`.
2. Reads a curated `source_map_50.csv`.
3. Validates required columns, source types, duplicate URLs, crawl methods, and URL shape.
4. Crawls only approved source URLs.
5. Stores page evidence with source URL, content hash, parser version, language, and status.
6. Extracts evidence-backed facts by source type.
7. Normalizes facts into Glowbal matching/product fields.
8. Exports QA CSVs and product CSVs using UTF-8 with BOM for Excel compatibility.

The crawler does not fabricate values. If a value cannot be extracted from evidence, it remains empty or `needs_review`.

## Quick Start

Validate the pilot input files:

```powershell
python ingest.py validate-sources --seed data/seed_universities_50.csv --sources data/source_map_50.csv
```

Run the full pilot pipeline:

```powershell
python ingest.py run-pilot --seed data/seed_universities_50.csv --sources data/source_map_50.csv --rankings data/rankings_import.csv --out-dir exports/pilot
```

Run one stage at a time:

```powershell
python ingest.py crawl-sources --sources data/source_map_50.csv --out-dir exports/pilot
python ingest.py suggest-sources --sources exports/pilot/sources.csv --out exports/pilot/source_suggestions.csv
python ingest.py build-source-map-candidates --sources exports/pilot/sources.csv --suggestions exports/pilot/source_suggestions.csv --out exports/pilot/source_map_50_candidates.csv
python ingest.py extract-facts --sources exports/pilot/sources.csv --evidence exports/pilot/evidence.csv --out-dir exports/pilot
python ingest.py build-profiles --seed data/seed_universities_50.csv --sources exports/pilot/sources.csv --facts exports/pilot/facts.csv --rankings data/rankings_import.csv --out-dir exports/pilot
```

Retry failed required sources without recrawling the whole batch:

```powershell
python ingest.py build-retry-source-map --sources exports/pilot_curated/sources.csv --out exports/pilot_curated/retry_required_sources.csv --source-types official_home,undergraduate_admissions,tuition_fees,english_requirements
python ingest.py crawl-sources --sources exports/pilot_curated/retry_required_sources.csv --out-dir exports/pilot_curated_retry_required --timeout 12
python ingest.py merge-crawl-outputs --base-sources exports/pilot_curated/sources.csv --base-evidence exports/pilot_curated/evidence.csv --retry-sources exports/pilot_curated_retry_required/sources.csv --retry-evidence exports/pilot_curated_retry_required/evidence.csv --out-dir exports/pilot_curated_merged
```

After building profiles, review:

- `source_repair_required.csv`: required source URLs still failing.
- `field_gap_report.csv`: missing must-have product fields per university.

Run tests:

```powershell
python -m unittest discover -s tests
```

## Main Inputs

- `data/seed_universities_50.csv`: one row per university in the pilot batch.
- `data/source_map_50.csv`: approved source URLs. The crawler only reads these URLs.
- `data/rankings_import.csv`: curated ranking import for QS/THE/ARWU values.

## Main Outputs

QA outputs:

- `exports/pilot/sources.csv`
- `exports/pilot/evidence.csv`
- `exports/pilot/facts.csv`
- `exports/pilot/programs.csv`
- `exports/pilot/qa_report.csv`
- `exports/pilot/pilot_quality_gate.csv`

Product outputs:

- `exports/pilot/university_product_profiles.csv`
- `exports/pilot/university_matching_tags.csv`
- `exports/pilot/university_writer_context.csv`
- `exports/pilot/universities_import.csv`

## Supabase Schema

The staging schema is in:

```text
schemas/02_new_ingestion_schema.sql
```

Load this only when the team is ready to persist pilot outputs into Supabase staging tables. Phase 1 does not change the existing app-facing `universities` table.
