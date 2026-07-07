-- Sponsor Radar — fixes: result diversity, verified sponsor mapping.
-- Run in the Supabase SQL editor.

-- ---------------------------------------------------------------------------
-- Fix 1: match_jobs v2 — cap results at 2 per company so one employer with
-- many openings can't flood the list, and order the final set by similarity.
-- ---------------------------------------------------------------------------
create or replace function match_jobs(
    query_embedding vector(384),
    match_count int default 15
)
returns table (
    job_id bigint,
    company text,
    title text,
    location text,
    url text,
    mentions_sponsorship boolean,
    sponsor_name text,
    similarity float
)
language sql stable as $$
    with ranked as (
        select
            j.id,
            j.company,
            j.title,
            j.location,
            j.url,
            j.mentions_sponsorship,
            s.name as sponsor_name,
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
    )
    select id, company, title, location, url,
           mentions_sponsorship, sponsor_name, similarity
    from ranked
    where company_rank <= 2
    order by similarity desc
    limit match_count;
$$;

-- ---------------------------------------------------------------------------
-- Fix 3: verified sponsor mapping. Fuzzy matching proposes; a human approves.
-- Once a company is in this table, its jobs always use the verified sponsor
-- row — fuzzy matching becomes a fallback for unmapped companies only.
-- ---------------------------------------------------------------------------
create table if not exists sponsor_overrides (
    company_slug  text primary key,          -- slug from the seed list
    company_name  text not null,
    sponsor_id    bigint not null references sponsors(id),
    verified_at   timestamptz not null default now(),
    note          text
);

-- Candidate finder used by the review script: top-k register entries by
-- trigram similarity against both legal and trading names.
create or replace function propose_sponsors(company_name text, k int default 3)
returns table (
    sponsor_id bigint,
    register_name text,
    trading_name text,
    town text,
    score float
)
language sql stable as $$
    select
        s.id,
        s.name,
        s.trading_name,
        s.town,
        greatest(
            similarity(s.normalised_name, lower(company_name)),
            coalesce(similarity(lower(s.trading_name), lower(company_name)), 0)
        ) as score
    from sponsors s
    where s.skilled_worker_a_rated
    order by score desc
    limit k;
$$;

-- Re-point already-fetched jobs once overrides are applied.
create or replace function apply_overrides_to_jobs()
returns int
language sql as $$
    with updated as (
        update jobs j
        set sponsor_id = o.sponsor_id
        from sponsor_overrides o
        where j.company_slug = o.company_slug
          and (j.sponsor_id is distinct from o.sponsor_id)
        returning 1
    )
    select count(*)::int from updated;
$$;
