"""
Sponsor Radar — all-sector job ingestion via the Adzuna API.

Pulls recent UK postings across many industries (healthcare, education,
engineering, finance, science — not just tech), so graduates from any
background get real coverage.

Key difference from the ATS pipeline: aggregator company names are messy,
so sponsor matching here is STRICT — a job only gets linked to a register
entry at >= 0.80 similarity. Unlinked jobs are stored but won't appear in
results until verified. A false "licensed sponsor" claim is worse than a
missing job.

Secrets required: SUPABASE_URL, SUPABASE_SERVICE_KEY,
ADZUNA_APP_ID, ADZUNA_APP_KEY (free at developer.adzuna.com).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import requests
from supabase import create_client

# Adzuna category tags -> broad sectors graduates actually come from.
CATEGORIES = [
    "it-jobs",
    "healthcare-nursing-jobs",
    "engineering-jobs",
    "scientific-qa-jobs",
    "accounting-finance-jobs",
    "teaching-jobs",
    "pr-advertising-marketing-jobs",
    "legal-jobs",
]
PAGES_PER_CATEGORY = 3     # x 50 results = up to 150 jobs/category/day
STRICT_THRESHOLD = 0.80    # aggregator names are messy; be conservative
PRUNE_AFTER_DAYS = 14      # keep the free-tier database lean

SPONSOR_HINTS = (
    "visa sponsorship", "sponsorship available", "skilled worker visa",
    "we can sponsor", "sponsorship offered",
)
NO_SPONSOR_HINTS = (
    "no visa sponsorship", "unable to sponsor", "cannot sponsor",
    "without sponsorship", "must have the right to work",
)


import re

SENIOR_RE = re.compile(
    r"\b(principal|staff engineer|head of|director|vp|vice president|chief|lead|senior|sr\.?)\b",
    re.IGNORECASE)
INTERN_RE = re.compile(r"\b(intern|internship|placement year|industrial placement)\b", re.IGNORECASE)
GRAD_RE = re.compile(r"\b(graduate|entry[- ]level|trainee|apprentice)\b", re.IGNORECASE)
JUNIOR_RE = re.compile(r"\b(junior|jnr)\b", re.IGNORECASE)


def classify_seniority(title: str) -> str:
    if SENIOR_RE.search(title):
        return "senior"
    if INTERN_RE.search(title):
        return "intern"
    if GRAD_RE.search(title):
        return "graduate"
    if JUNIOR_RE.search(title):
        return "junior"
    return "mid"


def classify_sponsorship(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in SPONSOR_HINTS) and not any(
        h in t for h in NO_SPONSOR_HINTS)


def main() -> None:
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not all([sb_url, sb_key, app_id, app_key]):
        sys.exit("Set SUPABASE_URL, SUPABASE_SERVICE_KEY, "
                 "ADZUNA_APP_ID, ADZUNA_APP_KEY")
    client = create_client(sb_url, sb_key)
    now = datetime.now(timezone.utc).isoformat()

    # Cache sponsor lookups — the same employers recur constantly.
    sponsor_cache: dict[str, int | None] = {}

    def strict_sponsor(company: str) -> int | None:
        if company in sponsor_cache:
            return sponsor_cache[company]
        sid = None
        try:
            cands = client.rpc("propose_sponsors",
                               {"company_name": company, "k": 1}).execute().data
            if cands and cands[0]["score"] >= STRICT_THRESHOLD:
                sid = cands[0]["sponsor_id"]
        except Exception:  # noqa: BLE001
            pass
        sponsor_cache[company] = sid
        return sid

    total, linked = 0, 0
    for cat in CATEGORIES:
        for page in range(1, PAGES_PER_CATEGORY + 1):
            url = (f"https://api.adzuna.com/v1/api/jobs/gb/search/{page}"
                   f"?app_id={app_id}&app_key={app_key}"
                   f"&results_per_page=50&category={cat}"
                   f"&max_days_old=7&sort_by=date&content-type=application/json")
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"  {cat} p{page}: fetch failed ({e})")
                break

            results = resp.json().get("results", [])
            if not results:
                break

            rows = []
            for j in results:
                company = ((j.get("company") or {}).get("display_name") or "").strip()
                if not company:
                    continue
                desc = j.get("description") or ""
                sid = strict_sponsor(company)
                rows.append({
                    "external_id": str(j["id"]),
                    "source": "adzuna",
                    "company": company[:200],
                    "company_slug": company.lower().replace(" ", "-")[:100],
                    "sponsor_id": sid,
                    "title": (j.get("title") or "")[:500],
                    "location": ((j.get("location") or {}).get("display_name") or "")[:300],
                    "is_uk": True,   # gb endpoint
                    "url": j.get("redirect_url") or "",
                    "description": desc[:15000],
                    "mentions_sponsorship": classify_sponsorship(desc),
                    "sponsorship_negative": any(h in desc.lower() for h in NO_SPONSOR_HINTS),
                    "seniority": classify_seniority(j.get("title") or ""),
                    "posted_at": j.get("created"),
                    "last_seen": now,
                })
                linked += sid is not None

            if rows:
                client.table("jobs").upsert(
                    rows, on_conflict="source,external_id").execute()
                total += len(rows)
            print(f"  {cat} p{page}: {len(rows)} jobs")
            time.sleep(0.5)   # respect free-tier rate limits

    # Prune stale rows so the free-tier database stays small.
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=PRUNE_AFTER_DAYS)).isoformat()
    try:
        pruned = client.table("jobs").delete().lt(
            "last_seen", cutoff).execute()
        print(f"Pruned {len(pruned.data or [])} jobs not seen in "
              f"{PRUNE_AFTER_DAYS} days.")
    except Exception as e:  # noqa: BLE001 — pruning is best-effort
        print(f"Prune skipped: {e}")

    print(f"\nAdzuna total upserted: {total:,} | "
          f"linked to verified/strict sponsor match: {linked:,} "
          f"({100 * linked / max(total, 1):.0f}%)")
    print("Unlinked jobs are stored but hidden from results by design.")


if __name__ == "__main__":
    main()
