-- ============================================================================
-- GLOWBAL V2 — FULL DATABASE SCHEMA
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)
-- This current data schema can be considered as old one for reference as I'm going to make changes
-- ============================================================================

-- ── 1. Universities table (imported from CSV) ──────────────────────────────

create table if not exists public.universities (
  id            bigserial primary key,
  country       text not null,
  name          text not null,
  local_name    text,
  type          text,                          -- Private / Public
  qs_rank       int,
  the_rank      int,
  arwu_rank     int,
  national_rank text,
  strengths     text,                          -- comma-separated or free text
  specific_insight text,
  teaching_style   text,
  international_environment text,
  gpa_range     text,
  english_requirement text,
  standardized_test   text,
  special_test  text,
  admission_difficulty text,
  accept_rate   text,
  application_deadline text,
  scholarship   text,
  tuition_usd   text,
  living_cost_usd text,
  housing       text,
  industry_connections text,
  internship_coop     text,
  employability       text,
  best_for      text,
  weaknesses    text,
  notes         text,
  created_at    timestamptz not null default now()
);

alter table public.universities enable row level security;

-- Authenticated users can read universities
create policy "Authenticated users can read universities"
  on public.universities for select
  to authenticated
  using (true);

-- Service role has full access
create policy "Service role full access to universities"
  on public.universities for all
  to service_role
  using (true)
  with check (true);


-- ── 2. Extend student_profiles with onboarding tracking ────────────────────

-- Add onboarding_completed columns (safe to run multiple times)
do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name = 'student_profiles'
      and column_name = 'onboarding_completed'
  ) then
    alter table public.student_profiles
      add column onboarding_completed boolean not null default false;
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name = 'student_profiles'
      and column_name = 'onboarding_completed_at'
  ) then
    alter table public.student_profiles
      add column onboarding_completed_at timestamptz;
  end if;
end $$;


-- ── 3. User universities (the "My Universities" shortlist) ─────────────────

create table if not exists public.user_universities (
  id              bigserial primary key,
  user_id         uuid not null references auth.users(id) on delete cascade,
  university_id   bigint not null references public.universities(id) on delete cascade,
  status          text not null default 'interested'
                  check (status in ('interested','applying','applied','offer','rejected','enrolled')),
  match_score     int,                         -- 0-100
  notes           text,
  added_at        timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  unique (user_id, university_id)
);

alter table public.user_universities enable row level security;

create policy "Users manage own university list"
  on public.user_universities for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);


-- ── 4. Application tasks ───────────────────────────────────────────────────

create table if not exists public.application_tasks (
  id                  bigserial primary key,
  user_university_id  bigint not null references public.user_universities(id) on delete cascade,
  title               text not null,
  description         text,
  category            text not null default 'general'
                      check (category in ('research','documents','tests','deadlines','visits','general')),
  deadline            date,
  is_completed        boolean not null default false,
  completed_at        timestamptz,
  sort_order          int not null default 0,
  tips                jsonb,                   -- { content: "markdown tips text" }
  created_at          timestamptz not null default now()
);

alter table public.application_tasks enable row level security;

create policy "Users manage own tasks"
  on public.application_tasks for all
  to authenticated
  using (
    exists (
      select 1 from public.user_universities uu
      where uu.id = application_tasks.user_university_id
        and uu.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from public.user_universities uu
      where uu.id = application_tasks.user_university_id
        and uu.user_id = auth.uid()
    )
  );


-- ── 5. Task templates (seeded defaults) ────────────────────────────────────

create table if not exists public.task_templates (
  id                      bigserial primary key,
  title                   text not null,
  description             text,
  category                text not null default 'general',
  relative_deadline_days  int not null default -30,   -- negative = before app deadline
  sort_order              int not null default 0,
  tips                    jsonb
);

alter table public.task_templates enable row level security;

create policy "Authenticated users can read task templates"
  on public.task_templates for select
  to authenticated
  using (true);

create policy "Service role full access to task templates"
  on public.task_templates for all
  to service_role
  using (true)
  with check (true);

-- Seed default templates
insert into public.task_templates (title, description, category, relative_deadline_days, sort_order, tips) values
  ('Research course details', 'Look up entry requirements, modules, and course structure on the university website.', 'research', -120, 1,
   '{"content": "Start by reading the official course page. Note down specific modules that interest you — mentioning these in your personal statement shows genuine engagement. Check if the course is accredited by relevant professional bodies."}'::jsonb),

  ('Attend open day or virtual event', 'Sign up for an open day, webinar, or virtual campus tour.', 'visits', -90, 2,
   '{"content": "Open days are a chance to ask questions directly to admissions staff and current students. Prepare 3-5 questions in advance. Take notes — these details can strengthen your application and personal statement."}'::jsonb),

  ('Request academic references', 'Ask teachers or professors for reference letters well in advance.', 'documents', -75, 3,
   '{"content": "Give your referees at least 4 weeks notice. Provide them with your CV, the course you are applying to, and key points you would like them to mention. A specific, detailed reference is far more powerful than a generic one."}'::jsonb),

  ('Draft personal statement', 'Write your first draft of the personal statement or statement of purpose.', 'documents', -60, 4,
   '{"content": "Start with why you are passionate about this subject. Then cover: relevant experience, skills you have developed, what attracts you to this specific course, and your future goals. Aim for 600-800 words for UCAS or 1-2 pages for US applications."}'::jsonb),

  ('Review personal statement with AI', 'Use the Glowbal AI writer to get feedback and improve your draft.', 'documents', -45, 5,
   '{"content": "Paste your draft into the AI writer tool. Focus on the suggestions around specificity, academic tone, and course fit. Accept changes that feel authentic to your voice — the goal is to strengthen your writing, not replace it."}'::jsonb),

  ('Prepare for standardized tests', 'Study for any required tests (IELTS, TOEFL, SAT, GRE, GMAT, etc.).', 'tests', -60, 6,
   '{"content": "Check the exact score requirements for your target course. Use official practice materials. For IELTS/TOEFL, focus on the section where you score lowest. Book your test date early — popular centres fill up fast."}'::jsonb),

  ('Take standardized test', 'Sit the required standardized test and request score reports be sent to universities.', 'tests', -40, 7,
   '{"content": "Arrive early and bring valid ID. Request official score reports to be sent directly to your target universities. Most scores take 2-3 weeks to arrive, so plan accordingly."}'::jsonb),

  ('Gather transcripts and certificates', 'Request official transcripts, diplomas, and any required certificates.', 'documents', -30, 8,
   '{"content": "Contact your school or university registrar. Some institutions take 2-4 weeks to process transcript requests. If documents are not in English, arrange for certified translations."}'::jsonb),

  ('Complete application form', 'Fill in the online application form with all required details.', 'deadlines', -14, 9,
   '{"content": "Double-check every field before submitting. Common mistakes: wrong start date, missing modules, inconsistent dates. Save a PDF copy of your completed application for your records."}'::jsonb),

  ('Submit application', 'Submit your completed application before the deadline.', 'deadlines', -1, 10,
   '{"content": "Submit at least 24 hours before the deadline to avoid technical issues. After submitting, save the confirmation email and any reference numbers. Some universities send a confirmation within a few days."}'::jsonb),

  ('Prepare for interview', 'If the university requires an interview, prepare answers and practice.', 'deadlines', 14, 11,
   '{"content": "Research common interview questions for your subject. Practice with a friend or family member. For Oxbridge-style interviews, focus on thinking out loud and problem-solving rather than memorised answers. Dress smart-casual for video interviews."}'::jsonb),

  ('Accept or decline offer', 'Review your offers and make your final decision.', 'deadlines', 60, 12,
   '{"content": "Compare offers side by side: course content, location, cost, scholarship, and gut feeling. If you have multiple offers, you may be able to negotiate financial aid. Respond before the deadline — late responses may forfeit your place."}'::jsonb)
on conflict do nothing;


-- ── 6. Personal statements (AI writer drafts) ─────────────────────────────

create table if not exists public.personal_statements (
  id                  bigserial primary key,
  user_id             uuid not null references auth.users(id) on delete cascade,
  user_university_id  bigint references public.user_universities(id) on delete set null,
  title               text not null default 'Untitled Draft',
  content             text not null default '',
  doc_type            text not null default 'personal_statement'
                      check (doc_type in ('personal_statement','statement_of_purpose')),
  ai_analysis         jsonb,                   -- { score, summary, suggestions[], checklist[] }
  version             int not null default 1,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

alter table public.personal_statements enable row level security;

create policy "Users manage own statements"
  on public.personal_statements for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);


-- ── 7. Indexes for performance ─────────────────────────────────────────────

create index if not exists idx_user_universities_user_id on public.user_universities(user_id);
create index if not exists idx_application_tasks_uu_id on public.application_tasks(user_university_id);
create index if not exists idx_personal_statements_user_id on public.personal_statements(user_id);
create index if not exists idx_universities_country on public.universities(country);
