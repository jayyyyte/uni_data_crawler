# Glowbal University Ingestion Data Dictionary

## Principles

- Evidence first: every extracted fact must include `evidence_id` and `source_url`.
- No fabrication: uncertain values are left blank and marked `needs_review`.
- Original text is preserved as UTF-8. Normalized fields are stored separately.
- Matching fields use controlled taxonomies, not free-form scraped text.
- Generated/advisory fields are marked for review.

## Input Files

### `seed_universities.csv`

Required columns:

- `university_id`: stable slug or UUID used across CSV files.
- `name`: official/common English name.
- `country`: country name.
- `city`: city name.
- `website_url`: official homepage.
- `type`: controlled value such as `public`, `private`, `specialist`, `unknown`.

Optional columns:

- `local_name`: original/local-script name.
- `region`: app/display region.
- `country_group`: broad matching region such as `Asia`, `Europe`, `North America`.
- `notes`: internal QA notes.

### `source_map.csv`

Required columns:

- `university_id`
- `university_name`
- `country`
- `source_type`
- `url`

Optional columns:

- `priority`: lower number means more important.
- `language_code`: BCP-47-ish code such as `en`, `zh-HK`, `ja`, `hu`.
- `crawl_method`: `static`, `playwright`, `pdf`, or `manual`.
- `notes`

Allowed `source_type` values:

- `official_home`
- `undergraduate_admissions`
- `graduate_admissions`
- `international_admissions`
- `program_catalog`
- `tuition_fees`
- `scholarships`
- `english_requirements`
- `cost_of_living`
- `housing`
- `career`
- `ranking`

## Staging Outputs

### `sources.csv`

Normalized source map with generated `source_id` and crawl `status`.

### `evidence.csv`

Crawled source text.

Important fields:

- `evidence_id`
- `source_id`
- `university_id`
- `url`
- `title`
- `language_code`
- `content_hash`
- `extracted_text`
- `retrieved_at`
- `parser_version`
- `status`
- `error`

### `facts.csv`

Evidence-backed facts.

Important fields:

- `fact_id`
- `university_id`
- `program_id`
- `fact_type`
- `fact_key`
- `value_text`
- `value_json`
- `value_number`
- `value_currency`
- `value_date`
- `evidence_id`
- `source_url`
- `supporting_text`: exact source quote for LLM-extracted facts.
- `confidence_score`
- `review_status`
- `extracted_at`

`fact_origin` values:

- `extracted_from_source`: deterministic/rule-based extraction from evidence.
- `llm_extracted_from_source`: OpenAI structured extraction from evidence; must include `supporting_text`.
- `inferred_from_text`: inferred tag from source text.
- `generated_by_rule`: advisory/generated tag from rules.
- `generated_by_llm`: reserved for advisory copy, not factual tuition/deadline/requirement data.
- `manual`: manually curated fact.

## Product Outputs

### `university_product_profiles.csv`

Flattened row per university for product/frontend QA.

Must-have pilot fields:

- `name`
- `country`
- `city`
- `website_url`
- `type`
- `subject_tags`
- `study_level_tags`
- `tuition_usd_min`
- `tuition_usd_max`
- `living_cost_usd_min`
- `living_cost_usd_max`
- `scholarship_available`
- `application_system`
- `deadline_summary`
- `english_requirement_summary`
- `cert_requirement_summary`: standardized/non-English proficiency certificates such as SAT, ACT, GRE, GMAT, IB, A-Level, HSK, JLPT, TOPIK.
- `cert_requirement_tags`: controlled cert tags.
- `portfolio_required`
- `interview_required`
- `data_quality_score`
- `import_status`
- `review_status`

`english_requirement_summary` is only for English proficiency evidence such as IELTS, TOEFL iBT, PTE, Duolingo, and Cambridge English. SAT/ACT/GRE/GMAT and similar certificates belong in `cert_requirement_summary`.

### Matching Taxonomies

Subject tags:

- `computer_science`
- `engineering`
- `business`
- `medicine`
- `law`
- `arts_design`
- `social_sciences`
- `natural_sciences`
- `humanities`
- `architecture`
- `education`
- `hospitality`
- `environment`

Study level tags:

- `foundation`
- `bachelor`
- `master`
- `phd`
- `mba`
- `medicine`
- `law`

Campus vibe tags:

- `urban`
- `suburban`
- `college_town`
- `campus_based`
- `research_heavy`
- `career_focused`
- `arts_friendly`
- `startup_focused`
- `competitive`
- `collaborative`
- `large_public`
- `small_private`

Support tags:

- `scholarship`
- `strong_international_office`
- `housing_support`
- `career_services`
- `coop_available`
- `internship_friendly`
- `english_support`
- `visa_support`
