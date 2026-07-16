"""
Sponsor Radar — Step 2b: fetch live jobs from verified company boards.

Reads data/verified_companies.csv, pulls every posting from each company's
ATS API, flags UK roles and sponsorship mentions, matches each company to
its sponsor register row, and upserts into the Supabase jobs table.

Run (after verify_seed.py):
    pip install requests supabase
    export SUPABASE_URL=... SUPABASE_SERVICE_KEY=...
    python fetch_jobs.py
"""

from __future__ import annotations

import csv
import html
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from supabase import create_client

VERIFIED = Path("data/verified_companies.csv")
TIMEOUT = 20
HEADERS = {"User-Agent": "SponsorRadar/0.1 (job aggregation for visa-sponsored roles)"}

UK_PATTERN = re.compile(
    r"\b(uk|united kingdom|london|manchester|birmingham|edinburgh|glasgow|"
    r"leeds|bristol|cambridge|oxford|belfast|cardiff|liverpool|newcastle|"
    r"sheffield|nottingham|reading|milton keynes|brighton|remote.{0,20}uk)\b",
    re.IGNORECASE,
)
SPONSOR_PATTERN = re.compile(
    r"\b(visa sponsorship|sponsor(ship)? (is )?(available|offered|provided)|"
    r"skilled worker visa|we (can|do|are able to) sponsor|"
    r"support.{0,20}visa|relocation.{0,30}visa)\b",
    re.IGNORECASE,
)
NO_SPONSOR_PATTERN = re.compile(
    r"\b(no visa sponsorship|unable to (provide|offer) (visa )?sponsor|"
    r"cannot sponsor|not able to sponsor|without (the need for )?sponsorship|"
    r"must have the right to work)\b",
    re.IGNORECASE,
)


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
    return "unknown"


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", html.unescape(text or ""))


def classify(location: str, description: str) -> tuple[bool, bool]:
    """Returns (is_uk, mentions_sponsorship). A negative sponsorship phrase
    overrides a positive one — 'no visa sponsorship' must not count as yes."""
    is_uk = bool(UK_PATTERN.search(location or ""))
    desc = strip_html(description)[:20000]
    mentions = bool(SPONSOR_PATTERN.search(desc)) and not NO_SPONSOR_PATTERN.search(desc)
    return is_uk, mentions


# --- Per-ATS fetchers, each yielding a common job dict ----------------------

def fetch_greenhouse(slug: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield {
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description": j.get("content", ""),
            "posted_at": j.get("updated_at"),
        }


def fetch_lever(slug: str):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    for j in r.json():
        cats = j.get("categories") or {}
        ts = j.get("createdAt")
        yield {
            "external_id": str(j["id"]),
            "title": j.get("text", ""),
            "location": cats.get("location", "") or "",
            "url": j.get("hostedUrl", ""),
            "description": j.get("descriptionPlain") or j.get("description", ""),
            "posted_at": (datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                          .isoformat() if ts else None),
        }


def fetch_ashby(slug: str):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    r.raise_for_status()
    for j in r.json().get("jobs", []):
        yield {
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            "location": j.get("location", "") or "",
            "url": j.get("jobUrl", "") or j.get("applyUrl", ""),
            "description": j.get("descriptionHtml") or "",
            "posted_at": j.get("publishedAt"),
        }


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    client = create_client(url, key)

    with VERIFIED.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    now = datetime.now(timezone.utc).isoformat()
    total, uk_total, sponsor_mention_total = 0, 0, 0

    # Verified mappings win; fuzzy matching is only a fallback for
    # companies no human has reviewed yet.
    overrides = {
        r["company_slug"]: r["sponsor_id"]
        for r in client.table("sponsor_overrides")
                        .select("company_slug,sponsor_id").execute().data
    }
    if overrides:
        print(f"Loaded {len(overrides)} verified sponsor mappings.")

    for c in companies:
        name, ats, slug = c["company"], c["ats"], c["slug"]

        # Resolve the sponsor register row once per company.
        sponsor_id = overrides.get(slug)
        if sponsor_id is None:
            try:
                resp = client.rpc("match_sponsor", {"company_name": name}).execute()
                sponsor_id = resp.data
            except Exception as e:  # noqa: BLE001 — log and continue
                print(f"  sponsor match failed for {name}: {e}")

        rows = []
        try:
            for job in FETCHERS[ats](slug):
                is_uk, mentions = classify(job["location"], job["description"])
                desc_plain = strip_html(job["description"])[:15000]
                rows.append({
                    "external_id": job["external_id"],
                    "source": ats,
                    "company": name,
                    "company_slug": slug,
                    "sponsor_id": sponsor_id,
                    "title": job["title"][:500],
                    "location": job["location"][:300],
                    "is_uk": is_uk,
                    "url": job["url"],
                    "description": desc_plain,
                    "mentions_sponsorship": mentions,
                    "sponsorship_negative": bool(NO_SPONSOR_PATTERN.search(desc_plain)),
                    "seniority": classify_seniority(job["title"]),
                    "posted_at": job["posted_at"],
                    "last_seen": now,
                })
        except requests.RequestException as e:
            print(f"  FETCH FAILED {name} ({ats}/{slug}): {e}")
            continue

        for i in range(0, len(rows), 200):
            client.table("jobs").upsert(
                rows[i:i + 200], on_conflict="source,external_id",
            ).execute()

        uk = sum(r["is_uk"] for r in rows)
        sm = sum(r["mentions_sponsorship"] for r in rows)
        total += len(rows); uk_total += uk; sponsor_mention_total += sm
        print(f"  {name:28} {len(rows):4} jobs | {uk:3} UK | "
              f"{sm:3} mention sponsorship | sponsor_id={sponsor_id}")
        time.sleep(0.3)

    print(f"\nTotal: {total:,} jobs | {uk_total:,} UK | "
          f"{sponsor_mention_total:,} mention sponsorship")


if __name__ == "__main__":
    main()
