# Sponsor Radar

Upload your CV. See only the UK jobs you can actually get a visa for.

Sponsor Radar joins live job postings against the Home Office Register of
Licensed Sponsors and the Skilled Worker salary rules, so graduates on the
Graduate visa stop wasting hours cross-referencing a 100,000-row CSV by hand.

## Status: Step 1 — sponsor register pipeline

- `ingest_sponsor_register.py` — downloads the latest register from gov.uk
  (link changes daily, so we scrape the publication page), cleans the messy
  data, normalises company names into a stable matching key, extracts T/A
  trading names, and collapses one-row-per-route duplicates into one row per
  company with an aggregated route list and an A-rated Skilled Worker flag.
- `schema.sql` — Supabase schema with trigram indexes ready for fuzzy
  company-name matching against job boards (Step 2).
- `upload_to_supabase.py` — upserts on the normalised name and stamps
  `last_seen`, so licence revocations show up as staleness instead of
  silently vanishing.
- `.github/workflows/refresh_register.yml` — free daily refresh.

## Why the cleaning matters

The register's only join key to the jobs world is the company name, and it
is messy: leading spaces, `T/A` trading names, towns spelled "Lodnon",
counties containing "Select a State". Job boards post under trading names
("Subway") while the register lists legal names ("1SA LIMITED T/A Subway").
The normalised key plus extracted trading name is what makes the later
matching step possible.

B-rated sponsors are kept but flagged: a B rating generally means the
company cannot issue new Certificates of Sponsorship, so they should not be
shown to users as viable targets.

## Setup

1. Create a free Supabase project, run `schema.sql` in the SQL editor.
2. Add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` as GitHub repo secrets.
3. Push — the workflow runs weekday mornings, or trigger it manually.

## Roadmap

1. ~~Sponsor register pipeline~~ (this step)
2. Job ingestion from Greenhouse/Lever/Ashby for sponsor-matched companies
3. CV upload + embedding-based matching
4. Claude-generated match explanations and sponsorship-confidence badges
5. Email digests, freemium accounts
