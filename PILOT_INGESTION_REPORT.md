# Glowbal University Ingestion Pilot Report

## 1. Executive Summary

Pilot này xây dựng ingestion pipeline cho 50 universities đầu tiên theo hướng **evidence-first staging + CSV QA**, chưa ghi thẳng vào bảng production `universities`.

Kết quả cuối nằm trong:

```text
exports/pilot_final/
```

Trạng thái hiện tại:

- Source rows: 367
- Successfully fetched sources: 345
- Failed sources: 22
- Universities with QS rank populated: 48/50
- Evidence link quality: pass, 100% facts có `evidence_id` và `source_url`
- Matching readiness: pass, 0.94
- Required source coverage: 0.76, chưa đạt target 0.90
- Average data quality score: 0.64, chưa đạt target 0.70

Hai lý do chính khiến quality gate chưa pass:

- `country_cost_of_living.csv` mới là template, chưa có số annual living cost.
- Một số field product như `application_system`, `deadline_summary`, `english_requirement_summary`, `tuition_usd_min/max` vẫn cần source tốt hơn hoặc extractor sâu hơn.

## 2. Final Files Team Should Check

Team QA/product nên bắt đầu từ các file sau:

```text
exports/pilot_final/university_product_profiles.csv
exports/pilot_final/universities_import.csv
exports/pilot_final/qa_report.csv
exports/pilot_final/pilot_quality_gate.csv
exports/pilot_final/field_gap_report.csv
exports/pilot_final/source_repair_remaining.csv
exports/pilot_final/sources.csv
exports/pilot_final/evidence.csv
exports/pilot_final/facts.csv
```

Ý nghĩa từng file:

- `university_product_profiles.csv`: output chính cho product review, matching, university cards, writer context.
- `universities_import.csv`: bản import-compatible cho bảng app-facing `universities`, sau khi team approve.
- `qa_report.csv`: score và missing fields theo từng university.
- `pilot_quality_gate.csv`: pass/fail tổng thể của batch 50.
- `field_gap_report.csv`: các field còn thiếu theo từng university.
- `source_repair_remaining.csv`: các required source vẫn failed sau static + Playwright.
- `sources.csv`: source map cuối cùng đã crawl.
- `evidence.csv`: raw extracted text/evidence.
- `facts.csv`: facts đã extract từ evidence.

Input quan trọng:

```text
data/seed_universities_50.csv
data/rankings_import.csv
data/country_cost_of_living.csv
exports/pilot_final/source_map_repaired.csv
exports/pilot_final/source_repair_applied.csv
```

## 3. Pipeline Method

Pipeline hiện tại chạy theo flow:

```text
seed_universities_50.csv
  -> source map / repaired source map
  -> crawl static or Playwright
  -> evidence.csv
  -> facts.csv
  -> normalized product profile CSVs
  -> QA reports
```

Các nguyên tắc chính:

- Crawler chỉ crawl URL trong source map hoặc repair source map.
- Không fabricate facts. Nếu không có evidence thì để trống hoặc `needs_review`.
- Mỗi fact phải có `evidence_id` và `source_url`.
- QS ranking được import riêng qua `rankings_import.csv`, không crawl từ university websites.
- Cost of living dùng country-level fallback qua `country_cost_of_living.csv`.
- Các website bị WAF/403/timeout có thể đặt `crawl_method=playwright`.

Các command quan trọng:

```powershell
python ingest.py validate-sources --seed data/seed_universities_50.csv --sources exports/pilot_final/source_map_repaired.csv
python ingest.py crawl-sources --sources exports/pilot_final/source_map_repaired.csv --out-dir exports/pilot_final_next --timeout 20
python ingest.py extract-facts --sources exports/pilot_final/sources.csv --evidence exports/pilot_final/evidence.csv --out-dir exports/pilot_final
python ingest.py build-profiles --seed data/seed_universities_50.csv --sources exports/pilot_final/sources.csv --facts exports/pilot_final/facts.csv --rankings data/rankings_import.csv --country-costs data/country_cost_of_living.csv --out-dir exports/pilot_final
```

## 4. Solution Details

### Source Repair Method

HTTP 404:

- Treat as likely stale URL.
- Replace with current official URL.
- Keep `crawl_method=static` unless page is JS-heavy.

403, WAF, SSL, timeout, bot protection:

- Treat as access/crawler issue, not necessarily wrong URL.
- Keep the URL if it is official and correct.
- Set `crawl_method=playwright`.

Repair file used:

```text
exports/pilot_final/source_repair_applied.csv
```

Remaining failed required sources:

```text
exports/pilot_final/source_repair_remaining.csv
```

### Ranking Method

QS rank is imported from curated data:

```text
data/rankings_import.csv
```

Current status:

- 48/50 universities have QS World University Rankings 2026 values.
- Bocconi is blank because QS lists subject/contributor status, not a QS WUR 2026 rank.
- KAIST is blank because QS says KAIST is excluded from QS WUR 2026.

### Country-Level Cost Of Living

Cost of living should be handled at country level:

```text
data/country_cost_of_living.csv
```

Expected behavior:

- One annual living-cost range per country.
- All universities in that country inherit the same range unless university-level evidence exists later.
- This reduces duplicated crawling and makes budget matching available earlier.

Current status:

- Template is created.
- Values are still blank.
- This is why `living_cost_usd_min/max` is missing for all 50 universities.

## 5. Database / Schema Organization

Do not overwrite production `public.universities` directly during ingestion.

New staging schema is defined in:

```text
schemas/02_new_ingestion_schema.sql
```

Recommended architecture:

### Trust Layer

Tables:

- `university_sources`
- `university_evidence`
- `university_facts`

Purpose:

- Track URL/source ownership.
- Store raw extracted evidence.
- Store structured facts with evidence linkage, confidence, review status.

### Program Layer

Table:

- `university_programs`

Purpose:

- Store program-level facts where available.
- Keep program-level tuition/deadline/requirements separate from university-level profile.

### Product Layer

Table:

- `university_product_profiles`

Purpose:

- Flattened profile for product/frontend.
- Used for discovery cards, matching, shortlist context, application tracker, AI writer context.

Current production `public.universities` remains the compatibility/import table for app usage.

## 6. Current Quality Snapshot

From `exports/pilot_final/pilot_quality_gate.csv`:

| Metric | Value | Target | Status |
| --- | ---: | ---: | --- |
| universities_with_required_sources | 0.76 | 0.90 | fail |
| facts_with_evidence_links | 1.00 | 1.00 | pass |
| average_data_quality_score | 0.64 | 0.70 | fail |
| matching_readiness_rate | 0.94 | 0.80 | pass |

Fact counts:

| Fact type | Count |
| --- | ---: |
| matching | 4237 |
| program | 318 |
| tuition | 126 |
| support | 72 |
| application | 53 |
| english_requirement | 47 |
| scholarship | 24 |

Main missing fields from `field_gap_report.csv`:

| Missing field | Count |
| --- | ---: |
| living_cost_usd_min | 50 |
| living_cost_usd_max | 50 |
| application_system | 36 |
| tuition_usd_min | 34 |
| tuition_usd_max | 34 |
| english_requirement_summary | 26 |
| scholarship_available | 26 |
| deadline_summary | 24 |
| study_level_tags | 3 |
| subject_tags | 3 |

## 7. What To Review Next

Recommended QA order:

1. Review `university_product_profiles.csv`
   - Check display name, country, city, rank, tags, tuition ranges.
   - Ignore living cost until `country_cost_of_living.csv` is filled.

2. Fill `country_cost_of_living.csv`
   - Add evidence-backed annual USD ranges per country.
   - Re-run `build-profiles`.

3. Review `source_repair_remaining.csv`
   - Fix the remaining failed URLs.
   - For PDF URLs, use `crawl_method=pdf` or add a non-PDF official page when available.
   - For timeouts/WAF, keep `playwright`.

4. Review `field_gap_report.csv`
   - Prioritize `tuition_usd_min/max`, `english_requirement_summary`, `deadline_summary`, `application_system`.

5. Only after QA approval, use:

```text
exports/pilot_final/universities_import.csv
```

as the app-facing import candidate.

## 8. Cleanup Performed

Removed intermediate export folders:

- `exports/pilot_homepages`
- `exports/pilot_candidates`
- `exports/pilot_curated`
- `exports/pilot_curated_retry`
- `exports/pilot_curated_retry_required`
- `exports/pilot_curated_merged`
- `exports/pilot_curated_merged_v2`
- `exports/pilot_repaired_playwright`

Kept:

- `exports/pilot_final`
- `data/`
- `schemas/`
- `glowbal_ingestion/`
- `tests/`
- root docs and schema reference files

