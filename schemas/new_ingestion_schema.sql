-- Glowbal university ingestion staging schema.
-- This schema is intentionally separate from the existing app-facing universities table.

create extension if not exists pgcrypto;

create table if not exists university_sources (
  id uuid primary key default gen_random_uuid(),
  university_id text,
  university_name text not null,
  country text,
  source_type text not null check (
    source_type in (
      'official_home',
      'undergraduate_admissions',
      'graduate_admissions',
      'international_admissions',
      'program_catalog',
      'tuition_fees',
      'scholarships',
      'english_requirements',
      'cost_of_living',
      'housing',
      'career',
      'ranking'
    )
  ),
  url text not null,
  priority int default 1,
  language_code text,
  crawl_method text default 'static' check (crawl_method in ('static', 'playwright', 'pdf', 'manual')),
  status text default 'pending' check (status in ('pending', 'fetched', 'failed', 'stale', 'manual', 'skipped')),
  last_crawled_at timestamptz,
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (university_id, source_type, url)
);

create index if not exists university_sources_university_idx
  on university_sources (university_id);

create index if not exists university_sources_source_type_idx
  on university_sources (source_type);

create table if not exists university_evidence (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references university_sources(id) on delete set null,
  university_id text,
  url text not null,
  title text,
  language_code text,
  content_hash text,
  extracted_text text,
  retrieved_at timestamptz default now(),
  parser_version text,
  status text default 'ok' check (status in ('ok', 'empty', 'failed', 'manual', 'unsupported_pdf', 'playwright_required')),
  error text,
  created_at timestamptz default now()
);

create index if not exists university_evidence_university_idx
  on university_evidence (university_id);

create index if not exists university_evidence_source_idx
  on university_evidence (source_id);

create index if not exists university_evidence_hash_idx
  on university_evidence (content_hash);

create table if not exists university_programs (
  id uuid primary key default gen_random_uuid(),
  university_id text not null,
  name text not null,
  normalized_name text,
  degree_level text,
  field_of_study text,
  faculty text,
  campus text,
  language_of_instruction text,
  program_url text,
  status text default 'active' check (status in ('active', 'inactive', 'needs_review')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index if not exists university_programs_university_idx
  on university_programs (university_id);

create table if not exists university_facts (
  id uuid primary key default gen_random_uuid(),
  university_id text,
  program_id uuid references university_programs(id) on delete set null,
  fact_type text not null,
  fact_key text not null,
  value_text text,
  value_json jsonb,
  value_number numeric,
  value_currency text,
  value_date date,
  evidence_id uuid references university_evidence(id) on delete set null,
  source_url text,
  confidence_score numeric check (confidence_score is null or (confidence_score >= 0 and confidence_score <= 1)),
  review_status text default 'needs_review' check (review_status in ('needs_review', 'approved', 'rejected', 'generated')),
  extracted_at timestamptz default now(),
  created_at timestamptz default now()
);

create index if not exists university_facts_university_idx
  on university_facts (university_id);

create index if not exists university_facts_type_key_idx
  on university_facts (fact_type, fact_key);

create index if not exists university_facts_evidence_idx
  on university_facts (evidence_id);

create table if not exists university_product_profiles (
  university_id text primary key,
  display_name text,
  local_name text,
  country text,
  city text,
  region text,
  country_group text,
  type text,
  website_url text,
  image_url text,
  short_description text,

  qs_rank int,
  the_rank int,
  arwu_rank int,
  rank_display text,

  subject_tags text[],
  study_level_tags text[],
  campus_vibe_tags text[],
  support_tags text[],

  tuition_usd_min int,
  tuition_usd_max int,
  living_cost_usd_min int,
  living_cost_usd_max int,
  total_cost_usd_min int,
  total_cost_usd_max int,
  scholarship_available boolean,

  application_system text,
  deadline_summary text,
  english_requirement_summary text,
  requirement_summary text,

  strengths text[],
  best_for text[],
  weaknesses text[],
  writer_context jsonb,

  evidence_coverage_score numeric,
  data_quality_score numeric,
  review_status text default 'draft' check (review_status in ('draft', 'needs_review', 'approved', 'rejected')),
  updated_at timestamptz default now()
);

create index if not exists university_product_profiles_country_idx
  on university_product_profiles (country);

create index if not exists university_product_profiles_review_idx
  on university_product_profiles (review_status);

