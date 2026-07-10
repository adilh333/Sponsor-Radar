# Sponsor Radar

**Upload your CV. See only the UK jobs that can actually sponsor you.**

Live: **sponsor-radar.vercel.app** &nbsp;·&nbsp; Built by [Adil Hussain](https://www.linkedin.com/in/adilhussain1996) — an international graduate in Manchester who got tired of Ctrl+F-ing a 125,000-row government spreadsheet for every job application.

---

## The problem

Graduates on the UK Graduate visa need a Skilled Worker sponsor before their visa expires. The Home Office publishes the register of licensed sponsors — but it is a 125,000-row CSV with no job links, no salary data, and no way to know whether a company is actually hiring. The manual routine for every single application: find a job → look up the company in the register → guess whether the salary clears the visa threshold → apply → hope.

Sponsor Radar automates the cross-referencing: live job postings, joined against the sponsor register daily, matched to your CV by meaning rather than keywords, with an honest confidence label on every result.

## How it works

```
gov.uk register ──► ingest & clean ──► Supabase (Postgres + pgvector)
                                          ▲                ▲
ATS APIs (Greenhouse/Lever/Ashby) ────────┘                │
Adzuna API (8 sectors) ───────────────────┘                │
        │                                                  │
        └── embed jobs (gte-small, GitHub Actions) ────────┘

User CV (PDF, parsed in-browser) ──► Edge Function embeds (same model)
        ──► pgvector cosine search ──► Claude API explains top matches
        ──► results with register verification + confidence bands
```

**Pipelines (all free-tier, fully automated via GitHub Actions):**

1. **Sponsor register** — daily download from gov.uk (the CSV URL changes every day, so the publication page is scraped for the current link). ~126k messy rows are cleaned, company names normalised into stable matching keys, `T/A` trading names extracted, per-route duplicates collapsed, and B-rated / provisional sponsors flagged as unable to issue new Certificates of Sponsorship. Companies that vanish from the register are detected via `last_seen` staleness rather than silent deletion — licence revocations are a signal.

2. **Jobs** — two tiers. High-confidence: direct from company ATS APIs (Greenhouse, Lever, Ashby) for a verified seed list of sponsor companies. Broad coverage: the Adzuna API across eight sectors (healthcare, teaching, engineering, science, finance, legal, marketing, IT). Sponsorship mentions are detected in descriptions, with negative phrases ("no visa sponsorship") deliberately overriding positive ones.

3. **Matching** — jobs are embedded with `gte-small` in GitHub Actions; the user's CV is embedded at request time by a Supabase Edge Function running the *same model*, so both live in one vector space. Search is pgvector cosine similarity with a 2-jobs-per-company cap so no single employer floods the results. Claude (Haiku) generates one specific sentence per top match explaining the fit.

## Design decisions worth reading

**A false "licensed sponsor" claim is the worst possible error.** Fuzzy company-name matching (trigram similarity) initially produced confident false positives — it matched the AI company Encord to an unrelated firm called "Encortec Limited", and a fintech's "Kraken" to "KRAKEN GROCERS LTD". The fix is a human-in-the-loop verification workflow: the system *proposes* register matches with similarity scores, a reviewer approves or rejects each one, and approved mappings are stored in an overrides table that always wins over fuzzy matching. Aggregator jobs use a strict 0.80 similarity threshold and are hidden from results entirely when unverified. Missing a job is annoying; showing a false sponsorship claim is a betrayal of the product's one promise.

**Similarity search fails silently on coverage gaps.** Cosine similarity always returns the nearest 15 jobs — even when nothing is actually relevant. An out-of-domain test CV (a dental/health-education background against a then tech-only job pool) returned confident-looking ML engineering matches. The fix: every result carries a calibrated confidence band (Strong / Moderate / Weak), and when nothing clears the bar the UI says so plainly instead of padding the list.

**Privacy by architecture.** CVs are parsed client-side (pdf.js in the browser), embedded once, matched, and discarded. No CV is ever stored — the landing-page claim is literally true.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, hand-rolled CSS, pdf.js |
| API | Next.js route handlers on Vercel |
| Database | Supabase Postgres + pgvector (HNSW), pg_trgm for fuzzy matching |
| Embeddings | gte-small — sentence-transformers in CI, Supabase Edge Function at request time |
| Explanations | Anthropic Claude API (Haiku) |
| Automation | GitHub Actions (daily register + jobs + embedding refresh) |
| Cost | £0/month infrastructure (free tiers) + pennies of Claude usage |

## Repository map

```
ingest_sponsor_register.py   gov.uk register download + cleaning
upload_to_supabase.py        register upsert with last_seen tracking
seed_companies.csv           121 UK sponsor companies with ATS slug candidates
verify_seed.py               probes Greenhouse/Lever/Ashby for live boards
fetch_jobs.py                ATS job ingestion + sponsorship detection
fetch_adzuna.py              all-sector ingestion, strict sponsor matching
sponsor_mapping.py           human-in-the-loop sponsor verification (propose/apply)
embed_jobs.py                batch job embeddings (gte-small)
schema.sql                   sponsors table + trigram indexes
jobs_schema.sql              jobs table + match function + live view
embeddings_schema.sql        pgvector + semantic match RPC
fixes_schema.sql             per-company caps + verified override table
supabase/functions/embed-cv  Edge Function: CV embedding at request time
web/                         Next.js app (landing, upload, results)
.github/workflows/           daily refresh pipelines
```

## Roadmap

- NHS Jobs and jobs.ac.uk ingestion (the largest sponsor employers in health and academia)
- Salary extraction vs Skilled Worker thresholds (new entrant vs standard rate)
- Accounts, saved CVs with consent, and daily email alerts (Pro tier)
- Company-level sponsorship history from Home Office transparency data

## Disclaimer

Sponsor Radar is an independent tool, not affiliated with the Home Office. A sponsor licence means an employer *can* sponsor — it never guarantees sponsorship for a specific role. Always confirm with the employer. Sponsor data: UK Home Office register of licensed sponsors (Workers), refreshed daily.
