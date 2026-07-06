-- Sponsor Radar — Step 3 schema: embeddings + semantic match.
-- Run in the Supabase SQL editor after jobs_schema.sql.

create extension if not exists vector;

alter table jobs add column if not exists embedding vector(384);

-- HNSW index for fast cosine search once the table grows.
create index if not exists jobs_embedding_idx
    on jobs using hnsw (embedding vector_cosine_ops);

-- The core product query: given a CV embedding, return the closest live
-- UK jobs at A-rated sponsors, with similarity and sponsorship signals.
create or replace function match_jobs(
    query_embedding vector(384),
    match_count int default 20
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
    select
        j.id,
        j.company,
        j.title,
        j.location,
        j.url,
        j.mentions_sponsorship,
        s.name,
        1 - (j.embedding <=> query_embedding) as similarity
    from jobs j
    join sponsors s on s.id = j.sponsor_id
    where j.is_uk
      and j.embedding is not null
      and j.last_seen >= now() - interval '3 days'
      and s.skilled_worker_a_rated
    order by j.embedding <=> query_embedding
    limit match_count;
$$;
