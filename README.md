# Glowbal University Data Ingestion

Evidence-first ingestion pipeline for Glowbal university data. The first phase is built to validate a pilot batch of 50 universities, export QA/product CSVs, and keep the existing app-facing `universities` table untouched until the data is approved.

## What This Pipeline Does

1. Reads a curated `seed_universities.csv`.
2. Reads a curated `source_map.csv`.
3. Validates required columns, source types, duplicate URLs, crawl methods, and URL shape.
4. Crawls only approved source URLs.
5. Stores page evidence with source URL, content hash, parser version, language, and status.
6. Extracts evidence-backed facts by source type.
7. Normalizes facts into Glowbal matching/product fields.
8. Exports QA CSVs and product CSVs using UTF-8 with BOM for Excel compatibility.

The crawler does not fabricate values. If a value cannot be extracted from evidence, it remains empty or `needs_review`.

English proficiency and certificate requirements are separated:

- `english_requirement_summary`: IELTS, TOEFL iBT, PTE, Duolingo, Cambridge English.
- `cert_requirement_summary`: SAT, ACT, GRE, GMAT, LSAT, MCAT, LNAT, UCAT, BMAT, TMUA, STEP, AP, IB, A-Level, HSK, JLPT, TOPIK.

## Optional API Keys

The baseline crawler and rule-based extractor use only the Python standard library. The one-off LLM-assisted workflow uses these optional environment variables:

```powershell
$env:SERPER_API_KEY="..."
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-4o-mini"
```

## Quick Start

Validate the pilot input files:

```powershell
python ingest.py validate-sources --seed data/seed_universities.csv --sources data/source_map.csv
```

Run the full pilot pipeline:

```powershell
python ingest.py run-pilot --seed data/seed_universities.csv --sources data/source_map.csv --rankings data/rankings_import.csv --country-costs data/country_cost_of_living.csv --out-dir exports/pilot
```

Run one stage at a time:

```powershell
python ingest.py crawl-sources --sources data/source_map.csv --out-dir exports/pilot
python ingest.py suggest-sources --sources exports/pilot/sources.csv --out exports/pilot/source_suggestions.csv
python ingest.py build-source-map-candidates --sources exports/pilot/sources.csv --suggestions exports/pilot/source_suggestions.csv --out exports/pilot/source_map_candidates.csv
python ingest.py extract-facts --sources exports/pilot/sources.csv --evidence exports/pilot/evidence.csv --out-dir exports/pilot
python ingest.py build-profiles --seed data/seed_universities.csv --sources exports/pilot/sources.csv --facts exports/pilot/facts.csv --rankings data/rankings_import.csv --country-costs data/country_cost_of_living.csv --evidence exports/pilot/evidence.csv --out-dir exports/pilot --run-id pilot_validated_v04
```

Run the one-off search + LLM-assisted workflow:

```powershell
python ingest.py search-sources --seed data/seed_universities.csv --existing-sources data/source_map.csv --out exports/scale_150/serper_source_candidates.csv --source-types undergraduate_admissions,tuition_fees,english_requirements,program_catalog,scholarships
python ingest.py promote-search-sources --seed data/seed_universities.csv --base-sources data/source_map.csv --candidates exports/scale_150/serper_source_candidates.csv --out exports/scale_150/source_map_llm_ready.csv
python ingest.py validate-sources --seed data/seed_universities.csv --sources exports/scale_150/source_map_llm_ready.csv
python ingest.py crawl-sources --sources exports/scale_150/source_map_llm_ready.csv --out-dir exports/scale_150/llm_ready_crawl --timeout 12
python ingest.py extract-facts --sources exports/scale_150/llm_ready_crawl/sources.csv --evidence exports/scale_150/llm_ready_crawl/evidence.csv --out-dir exports/scale_150/llm_ready_crawl
python ingest.py extract-facts-llm --sources exports/scale_150/llm_ready_crawl/sources.csv --evidence exports/scale_150/llm_ready_crawl/evidence.csv --out-dir exports/scale_150/llm_ready_crawl --run-id scale150_llm_v01
python ingest.py build-profiles --seed data/seed_universities.csv --sources exports/scale_150/llm_ready_crawl/sources.csv --facts exports/scale_150/llm_ready_crawl/facts.csv --rankings data/rankings_import.csv --country-costs data/country_cost_of_living.csv --evidence exports/scale_150/llm_ready_crawl/evidence.csv --out-dir exports/scale_150/llm_ready_crawl --run-id scale150_llm_v01
```

Review `serper_source_candidates.csv` before promotion. Only rows with `review_status=approved` are promoted.

Retry failed required sources without recrawling the whole batch:

```powershell
python ingest.py build-retry-source-map --sources exports/pilot_curated/sources.csv --out exports/pilot_curated/retry_required_sources.csv --source-types official_home,undergraduate_admissions,tuition_fees,english_requirements
python ingest.py crawl-sources --sources exports/pilot_curated/retry_required_sources.csv --out-dir exports/pilot_curated_retry_required --timeout 12
python ingest.py merge-crawl-outputs --base-sources exports/pilot_curated/sources.csv --base-evidence exports/pilot_curated/evidence.csv --retry-sources exports/pilot_curated_retry_required/sources.csv --retry-evidence exports/pilot_curated_retry_required/evidence.csv --out-dir exports/pilot_curated_merged
```

Apply manually reviewed source repairs:

```powershell
python ingest.py apply-source-repairs --seed data/seed_universities.csv --base-sources exports/pilot_validated/source_map_repaired.csv --repairs exports/pilot_validated/source_repair_remaining_fix.csv --out exports/pilot_validated/source_map_repaired_v04.csv
```

After building profiles, review:

- `source_repair_remaining.csv`: required source URLs still failing.
- `source_map_repaired_v04.csv`: repaired source map for the next retry crawl.
- `field_gap_report.csv`: missing must-have product fields per university.
- `run_manifest.json`: run metadata, input/output files, row counts, and quality gate summary.

Run tests:

```powershell
python -m unittest discover -s tests
```

## Main Inputs

- `data/seed_universities.csv`: one row per university in the active batch.
- `data/source_map.csv`: approved source URLs. The crawler only reads these URLs.
- `data/rankings_import.csv`: curated ranking import for QS/THE/ARWU values.
- `data/country_cost_of_living.csv`: country-level annual living-cost fallback used for budget matching.

## Main Outputs

QA outputs:

- `exports/pilot/sources.csv`
- `exports/pilot/evidence.csv`
- `exports/pilot/facts.csv`
- `exports/pilot/facts_llm.csv`
- `exports/pilot/llm_extraction_report.csv`
- `exports/pilot/programs.csv`
- `exports/pilot/qa_report.csv`
- `exports/pilot/pilot_quality_gate.csv`
- `exports/pilot/batch_qa_report.csv`
- `exports/pilot/field_gap_report.csv`
- `exports/pilot/run_manifest.json`

Product outputs:

- `exports/pilot/university_product_profiles.csv`
- `exports/pilot/university_matching_tags.csv`
- `exports/pilot/university_writer_context.csv`
- `exports/pilot/universities_import.csv`

## Supabase Schema

The staging schema is in:

```text
schemas/new_ingestion_schema.sql
```

Load this only when the team is ready to persist pilot outputs into Supabase staging tables. It creates an `ingestion` schema and does not change the existing app-facing `public.universities` table.
