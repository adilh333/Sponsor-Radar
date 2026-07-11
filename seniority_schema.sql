-- Sponsor Radar — seniority matching + explicit-refusal exclusion.
-- Run in the Supabase SQL editor.

alter table jobs add column if not exists seniority text default 'unknown';
alter table jobs add column if not exists sponsorship_negative boolean not null default false;

-- Backfill seniority for existing jobs from titles. Order matters:
-- senior signals are checked before graduate signals.
update jobs set seniority = case
    when title ~* '\y(principal|staff engineer|head of|director|vp |vice president|chief|lead)\y' then 'senior'
    when title ~* '\y(senior|sr\.?)\y' then 'senior'
    when title ~* '\y(intern|internship|placement year|industrial placement)\y' then 'intern'
    when title ~* '\y(graduate|entry[- ]level|trainee|apprentice)\y' then 'graduate'
    when title ~* '\y(junior|jnr)\y' then 'junior'
    else 'mid'
end;

-- Backfill explicit sponsorship refusals from descriptions.
update jobs set sponsorship_negative = true
where description ~* '(no visa sponsorship|unable to (provide|offer) (visa )?sponsor|cannot sponsor|not able to sponsor|without (the need for )?sponsorship|must (already )?have the right to work)';

create index if not exists jobs_seniority_idx on jobs (seniority);

-- match_jobs v3: seniority-aware, refusals excluded, optional strict mode.
create or replace function match_jobs(
    query_embedding vector(384),
    match_count int default 15,
    allowed_seniorities text[] default null,
    require_stated_sponsorship boolean default false
)
returns table (
    job_id bigint,
    company text,
    title text,
    location text,
    url text,
    mentions_sponsorship boolean,
    sponsor_name text,
    seniority text,
    similarity float
)
language sql stable as $$
    with ranked as (
        select
            j.id, j.company, j.title, j.location, j.url,
            j.mentions_sponsorship, s.name as sponsor_name, j.seniority,
            1 - (j.embedding <=> query_embedding) as similarity,
            row_number() over (
                partition by j.company
                order by j.embedding <=> query_embedding
            ) as company_rank
        from jobs j
        join sponsors s on s.id = j.sponsor_id
        where j.is_uk
          and j.embedding is not null
          and j.last_seen >= now() - interval '3 days'
          and s.skilled_worker_a_rated
          and not j.sponsorship_negative              -- never show refusals
          and (allowed_seniorities is null
               or j.seniority = any(allowed_seniorities)
               or j.seniority = 'unknown')
          and (not require_stated_sponsorship or j.mentions_sponsorship)
    )
    select id, company, title, location, url,
           mentions_sponsorship, sponsor_name, seniority, similarity
    from ranked
    where company_rank <= 2
    order by similarity desc
    limit match_count;
$$;
