# Glowbal University Ingestion Pilot Report

## 1. Executive Summary

The current pilot output is:

```text
exports/pilot_validated/
```

This is still a staging/QA dataset, not a production Supabase import. The pipeline now uses evidence quality gates, fact-origin separation, country-level living-cost fallback, product summary cleaning, and final product-profile import statuses.

Current run:

- Run ID: `pilot_validated_v05`
- Source rows: 367
- Evidence rows: 367
- Usable evidence rows: 310
- Non-usable evidence rows: 57
- Fact rows: 2,993
- Product profile rows: 50
- QS rank populated: 48/50
- Facts with `evidence_id` + `source_url`: 100%
- Matching readiness: 0.92, pass
- Average data quality score: 0.70, pass
- Required source coverage: 0.46, fail
- Product summary raw marker rows: 0
- Import status: 46 `internal_preview`, 4 `identity_only`

The main remaining blocker is not source-map shape. It is fact depth: `tuition_usd_min/max`, `deadline_summary`, `english_requirement_summary`, `cert_requirement_summary`, and `application_system` still need better usable evidence or stronger extractors before production import.

## 2. Files Team Should Check

Review these files first:

```text
exports/pilot_validated/run_manifest.json
exports/pilot_validated/university_product_profiles.csv
exports/pilot_validated/universities_import.csv
exports/pilot_validated/batch_qa_report.csv
exports/pilot_validated/pilot_quality_gate.csv
exports/pilot_validated/field_gap_report.csv
exports/pilot_validated/sources.csv
exports/pilot_validated/evidence.csv
exports/pilot_validated/facts.csv
exports/pilot_validated/facts_extracted.csv
exports/pilot_validated/facts_generated.csv
exports/pilot_validated/source_repair_remaining.csv
exports/pilot_validated/source_map_repaired_v04.csv
```

File meanings:

- `run_manifest.json`: run metadata, input/output files, row counts, quality gates.
- `university_product_profiles.csv`: main product-review output.
- `universities_import.csv`: import-shaped output, but still staging only.
- `batch_qa_report.csv`: per-university QA status.
- `pilot_quality_gate.csv`: batch-level pass/fail metrics.
- `field_gap_report.csv`: missing must-have fields by university.
- `evidence.csv`: crawled text with content quality classifier.
- `facts.csv`: all facts after validation gates.
- `facts_extracted.csv`: extracted/manual facts only.
- `facts_generated.csv`: inferred/generated matching facts.
- `source_map_repaired_v04.csv`: repaired source map from manual fix notes, for the next retry crawl.

## 3. Method And Schema

Pipeline flow:

```text
seed_universities.csv
  -> curated/repaired source map
  -> crawl static or Playwright
  -> classify evidence quality
  -> extract evidence-backed facts only from usable evidence
  -> normalize product profiles
  -> clean product summaries
  -> validate final product fields
  -> export QA/product CSVs + run manifest
```

Important rules:

- Do not extract facts from evidence where `content_quality_status != usable`.
- Do not fabricate facts. Missing or uncertain fields stay blank or review-required.
- Every fact must have `evidence_id` and `source_url`.
- QS ranking is imported from `data/rankings_import.csv`.
- Living cost uses `data/country_cost_of_living.csv` as country-level fallback.
- English proficiency stays in `english_requirement_summary`; SAT/ACT/GRE/GMAT/IB/A-Level/HSK/JLPT/TOPIK style requirements stay in `cert_requirement_summary`.
- App-facing production table remains unchanged.

Schema file:

```text
schemas/new_ingestion_schema.sql
```

The schema now creates an `ingestion` schema for staging tables. It does not modify `public.universities`.

## 4. Current Quality Snapshot

Quality gates:

| metric | value | threshold | status |
| --- | ---: | ---: | --- |
| universities_with_required_sources | 0.46 | 0.90 | fail |
| facts_with_evidence_links | 1.00 | 1.00 | pass |
| average_data_quality_score | 0.70 | 0.70 | pass |
| matching_readiness_rate | 0.92 | 0.80 | pass |

Missing product fields:

| field | missing rows |
| --- | ---: |
| tuition_usd_min | 44 |
| tuition_usd_max | 44 |
| deadline_summary | 41 |
| english_requirement_summary | 39 |
| cert_requirement_summary | 43 |
| application_system | 36 |
| scholarship_available | 26 |
| subject_tags | 0 |
| study_level_tags | 0 |
| living_cost_usd_min | 0 |
| living_cost_usd_max | 0 |

QA statuses:

| qa_status | rows |
| --- | ---: |
| ready_for_internal_preview | 46 |
| needs_fact_repair | 4 |

## 5. Next Recommended Work

Do not import production yet.

Recommended next steps:

1. Retry crawl using `exports/pilot_validated/source_map_repaired_v04.csv`.
2. Merge retry crawl outputs into the validated batch.
3. Re-run `extract-facts` and `build-profiles`.
4. Prioritize fact repair for tuition, deadline, English requirement, cert requirement, and application system.
5. Review `field_gap_report.csv` and `batch_qa_report.csv`.
6. Only consider batch 150 after product summaries remain clean and internal-preview rows stay above 25-35 with improved fact coverage.

Production import rule:

- `ready_for_import`: can be considered for import after human review.
- `internal_preview`: usable for internal product QA only.
- `identity_only`: keep for source/debug context, do not import.
- `do_not_import`: exclude.
