from __future__ import annotations

PARSER_VERSION = "glowbal-ingestion/0.1.0"

SOURCE_TYPES = {
    "official_home",
    "undergraduate_admissions",
    "graduate_admissions",
    "international_admissions",
    "program_catalog",
    "tuition_fees",
    "scholarships",
    "english_requirements",
    "cost_of_living",
    "housing",
    "career",
    "ranking",
}

CRAWL_METHODS = {"static", "playwright", "pdf", "manual"}

SOURCE_COLUMNS = [
    "source_id",
    "university_id",
    "university_name",
    "country",
    "source_type",
    "url",
    "priority",
    "language_code",
    "crawl_method",
    "status",
    "last_crawled_at",
    "notes",
]

SEED_COLUMNS = [
    "university_id",
    "name",
    "local_name",
    "country",
    "city",
    "region",
    "country_group",
    "website_url",
    "type",
    "notes",
]

EVIDENCE_COLUMNS = [
    "evidence_id",
    "source_id",
    "university_id",
    "url",
    "title",
    "language_code",
    "content_hash",
    "extracted_text",
    "retrieved_at",
    "parser_version",
    "fetch_status",
    "content_quality_status",
    "content_quality_reason",
    "text_len",
    "content_signal_score",
    "status",
    "error",
]

FACT_COLUMNS = [
    "fact_id",
    "university_id",
    "program_id",
    "fact_type",
    "fact_key",
    "value_text",
    "value_json",
    "value_number",
    "value_currency",
    "value_date",
    "fact_origin",
    "evidence_id",
    "source_url",
    "confidence_score",
    "review_status",
    "extracted_at",
]

BATCH_QA_COLUMNS = [
    "university_id",
    "display_name",
    "source_count",
    "usable_evidence_count",
    "blocked_evidence_count",
    "failed_source_count",
    "tuition_fact_count",
    "valid_tuition_fact_count",
    "deadline_fact_count",
    "valid_deadline_fact_count",
    "english_fact_count",
    "valid_english_fact_count",
    "matching_tag_count",
    "has_product_profile",
    "import_status",
    "qa_status",
    "qa_notes",
]

PROGRAM_COLUMNS = [
    "program_id",
    "university_id",
    "name",
    "normalized_name",
    "degree_level",
    "field_of_study",
    "faculty",
    "campus",
    "language_of_instruction",
    "program_url",
    "status",
]

PRODUCT_COLUMNS = [
    "university_id",
    "display_name",
    "local_name",
    "country",
    "city",
    "region",
    "country_group",
    "type",
    "website_url",
    "image_url",
    "short_description",
    "qs_rank",
    "the_rank",
    "arwu_rank",
    "rank_display",
    "subject_tags",
    "study_level_tags",
    "campus_vibe_tags",
    "support_tags",
    "tuition_usd_min",
    "tuition_usd_max",
    "living_cost_usd_min",
    "living_cost_usd_max",
    "total_cost_usd_min",
    "total_cost_usd_max",
    "scholarship_available",
    "application_system",
    "deadline_summary",
    "english_requirement_summary",
    "requirement_summary",
    "strengths",
    "best_for",
    "weaknesses",
    "writer_context",
    "evidence_coverage_score",
    "data_quality_score",
    "import_status",
    "review_status",
]

COUNTRY_COST_COLUMNS = [
    "country",
    "country_code",
    "annual_living_usd_min",
    "annual_living_usd_max",
    "currency",
    "source_url",
    "source_type",
    "confidence_score",
    "retrieved_at",
    "review_status",
    "notes",
]

MATCHING_COLUMNS = [
    "university_id",
    "subject_tags",
    "study_level_tags",
    "campus_vibe_tags",
    "support_tags",
    "tuition_usd_min",
    "tuition_usd_max",
    "living_cost_usd_min",
    "living_cost_usd_max",
    "total_cost_usd_min",
    "total_cost_usd_max",
]

WRITER_CONTEXT_COLUMNS = [
    "university_id",
    "writer_context",
    "strengths",
    "best_for",
    "weaknesses",
    "review_status",
]

QA_COLUMNS = [
    "university_id",
    "name",
    "source_count",
    "required_source_coverage",
    "evidence_count",
    "fact_count",
    "missing_must_have_fields",
    "evidence_coverage_score",
    "data_quality_score",
    "review_status",
]

QUALITY_GATE_COLUMNS = [
    "metric",
    "value",
    "threshold",
    "status",
    "notes",
]

FIELD_GAP_COLUMNS = [
    "university_id",
    "display_name",
    "missing_field",
    "import_status",
]

REQUIRED_SOURCE_TYPES = {
    "official_home",
    "undergraduate_admissions",
    "tuition_fees",
    "english_requirements",
}

MUST_HAVE_PRODUCT_FIELDS = [
    "display_name",
    "country",
    "city",
    "website_url",
    "type",
    "subject_tags",
    "study_level_tags",
    "tuition_usd_min",
    "tuition_usd_max",
    "living_cost_usd_min",
    "living_cost_usd_max",
    "scholarship_available",
    "application_system",
    "deadline_summary",
    "english_requirement_summary",
    "data_quality_score",
    "review_status",
]

SUBJECT_KEYWORDS = {
    "computer_science": [
        "computer science",
        "computing",
        "software",
        "artificial intelligence",
        "data science",
        "informatics",
    ],
    "engineering": ["engineering", "mechanical", "electrical", "civil engineering"],
    "business": ["business", "management", "finance", "accounting", "economics", "mba"],
    "medicine": ["medicine", "medical", "health sciences", "nursing", "biomedical"],
    "law": ["law", "legal studies", "juris"],
    "arts_design": ["art", "design", "fine arts", "creative", "media"],
    "social_sciences": ["social science", "sociology", "politics", "psychology", "anthropology"],
    "natural_sciences": ["science", "physics", "chemistry", "biology", "mathematics"],
    "humanities": ["humanities", "history", "philosophy", "literature", "languages"],
    "architecture": ["architecture", "built environment"],
    "education": ["education", "teaching"],
    "hospitality": ["hospitality", "tourism", "hotel"],
    "environment": ["environment", "sustainability", "climate", "earth sciences"],
}

STUDY_LEVEL_KEYWORDS = {
    "foundation": ["foundation", "pathway"],
    "bachelor": ["undergraduate", "bachelor", "bachelors", "ba ", "bsc", "b.a.", "b.s."],
    "master": ["graduate", "postgraduate", "master", "masters", "msc", "ma ", "m.a.", "m.s."],
    "phd": ["phd", "ph.d", "doctoral", "doctorate"],
    "mba": ["mba", "master of business administration"],
    "medicine": ["medicine", "mbbs", "md "],
    "law": ["llb", "jd ", "juris doctor", "law"],
}

VIBE_KEYWORDS = {
    "urban": ["urban", "city", "downtown", "metropolitan"],
    "suburban": ["suburban"],
    "college_town": ["college town", "university town"],
    "campus_based": ["campus-based", "residential campus", "campus life"],
    "research_heavy": ["research-intensive", "research university", "research excellence"],
    "career_focused": ["employability", "career-focused", "career readiness"],
    "arts_friendly": ["arts", "creative community"],
    "startup_focused": ["startup", "entrepreneurship", "innovation hub"],
    "competitive": ["competitive admission", "highly selective"],
    "collaborative": ["collaborative", "team-based"],
    "large_public": ["public university", "large public"],
    "small_private": ["small private", "private university"],
}

SUPPORT_KEYWORDS = {
    "scholarship": ["scholarship", "financial aid", "bursary", "grant"],
    "strong_international_office": ["international office", "international student support"],
    "housing_support": ["housing", "accommodation", "residence"],
    "career_services": ["career services", "careers service", "employability"],
    "coop_available": ["co-op", "cooperative education", "work-integrated"],
    "internship_friendly": ["internship", "placement"],
    "english_support": ["english language support", "academic english"],
    "visa_support": ["visa", "immigration advice"],
}

APPLICATION_SYSTEM_KEYWORDS = {
    "ucas": ["ucas"],
    "common_app": ["common app", "common application"],
    "ouac": ["ouac"],
    "coalition_app": ["coalition application", "coalition app"],
    "direct": ["apply direct", "direct application", "online application portal"],
    "school_portal": ["applicant portal", "application portal"],
}

CURRENCY_TO_USD = {
    "USD": 1.0,
    "US$": 1.0,
    "$": 1.0,
    "GBP": 1.25,
    "£": 1.25,
    "EUR": 1.08,
    "€": 1.08,
    "CAD": 0.74,
    "C$": 0.74,
    "AUD": 0.66,
    "A$": 0.66,
    "SGD": 0.74,
    "S$": 0.74,
    "HKD": 0.13,
    "HK$": 0.13,
    "JPY": 0.0065,
    "¥": 0.0065,
    "CNY": 0.14,
    "RMB": 0.14,
    "CHF": 1.10,
}
