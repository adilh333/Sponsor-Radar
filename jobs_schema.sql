-- Sponsor Radar — Step 2 schema: jobs table + sponsor matching.
-- Run in the Supabase SQL editor after schema.sql.

create table if not exists jobs (
    id                  bigint generated always as identity primary key,
    external_id         text not null,          -- ATS job id
    source              text not null,          -- greenhouse | lever | ashby
    company             text not null,          -- display name from seed list
    company_slug        text not null,
    sponsor_id          bigint references sponsors(id),
    title               text not null,
    location            text,
    is_uk               boolean not null default false,
    url                 text not null,
    description         text,
    mentions_sponsorship boolean not null default false,
    posted_at           timestamptz,
    first_seen          timestamptz not null default now(),
    last_seen           timestamptz not null default now(),
    unique (source, external_id)
);

create index if not exists jobs_uk_idx on jobs (is_uk) where is_uk;
create index if not exists jobs_sponsor_idx on jobs (sponsor_id);
create index if not exists jobs_last_seen_idx on jobs (last_seen);

-- Fuzzy sponsor lookup: given a company name, return the best register
-- match above a similarity threshold. Uses the trigram indexes from step 1.
create or replace function match_sponsor(company_name text)
returns bigint
language sql stable as $$
    select id from sponsors
    where skilled_worker_a_rated
      and (
        similarity(normalised_name, lower(company_name)) > 0.45
        or (trading_name is not null
            and similarity(lower(trading_name), lower(company_name)) > 0.45)
      )
    order by greatest(
        similarity(normalised_name, lower(company_name)),
        coalesce(similarity(lower(trading_name), lower(company_name)), 0)
    ) desc
    limit 1;
$$;

-- What the product ultimately shows: live UK jobs at A-rated sponsors.
create or replace view live_sponsored_jobs as
    select j.*, s.name as sponsor_register_name, s.ratings
    from jobs j
    join sponsors s on s.id = j.sponsor_id
    where j.is_uk
      and j.last_seen >= now() - interval '3 days'
      and s.skilled_worker_a_rated;
