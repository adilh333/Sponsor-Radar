"""
Sponsor Radar — Step 2a: verify which seed companies have live ATS boards.

For every company in seed_companies.csv, tries each candidate slug against
Greenhouse, Lever, and Ashby public job APIs. Writes verified_companies.csv
containing only live boards, with job counts, and reports misses so slugs
can be fixed by hand.

Also cross-checks each verified company against the Supabase sponsors table
(if credentials are set) so we know the sponsor join will work later.

Run:
    pip install requests supabase
    python verify_seed.py
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path

import requests

SEED = Path("seed_companies.csv")
OUT = Path("data/verified_companies.csv")
TIMEOUT = 15
HEADERS = {"User-Agent": "SponsorRadar/0.1 (job aggregation for visa-sponsored roles)"}


def try_greenhouse(slug: str) -> int | None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    if r.status_code == 200:
        return len(r.json().get("jobs", []))
    return None


def try_lever(slug: str) -> int | None:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list):
            return len(data)
    return None


def try_ashby(slug: str) -> int | None:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        jobs = data.get("jobs")
        if jobs is not None:
            return len(jobs)
    return None


PROBES = {
    "greenhouse": try_greenhouse,
    "lever": try_lever,
    "ashby": try_ashby,
}


def verify_company(name: str, slugs: list[str], hints: list[str]) -> dict | None:
    """Try hinted ATSes first, then the rest. First live hit wins."""
    order = [a for a in hints if a in PROBES] + [a for a in PROBES if a not in hints]
    for slug in slugs:
        for ats in order:
            try:
                count = PROBES[ats](slug)
            except requests.RequestException:
                count = None
            if count is not None:
                return {"company": name, "ats": ats, "slug": slug, "live_jobs": count}
            time.sleep(0.2)  # be polite
    return None


def check_sponsor_match(names: list[str]) -> dict[str, bool]:
    """Optional: confirm each company matches a row in the sponsors table."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("(Skipping sponsor cross-check — Supabase creds not set)")
        return {}
    from supabase import create_client
    client = create_client(url, key)
    result: dict[str, bool] = {}
    for name in names:
        # Trigram-backed fuzzy lookup: is this company on the register?
        needle = name.lower().replace(".", "").replace("&", "and")
        resp = (client.table("sponsors")
                .select("normalised_name")
                .ilike("normalised_name", f"%{needle.split()[0]}%")
                .limit(5).execute())
        result[name] = bool(resp.data)
    return result


def main() -> None:
    verified, missed = [], []
    with SEED.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"Verifying {len(rows)} companies against 3 ATS APIs...")
    for i, row in enumerate(rows, 1):
        name = row["company"].strip()
        slugs = [s.strip() for s in row["candidate_slugs"].split("|") if s.strip()]
        hints = [h.strip() for h in row["ats_hints"].split("|") if h.strip()]
        hit = verify_company(name, slugs, hints)
        if hit:
            hit["category"] = row["category"]
            verified.append(hit)
            print(f"  [{i:3}/{len(rows)}] OK   {name:28} {hit['ats']:11} "
                  f"slug={hit['slug']:24} jobs={hit['live_jobs']}")
        else:
            missed.append(name)
            print(f"  [{i:3}/{len(rows)}] MISS {name}")

    sponsor_hits = check_sponsor_match([v["company"] for v in verified])

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", "category", "ats", "slug", "live_jobs",
                    "on_sponsor_register"])
        for v in verified:
            w.writerow([v["company"], v["category"], v["ats"], v["slug"],
                        v["live_jobs"], sponsor_hits.get(v["company"], "")])

    print(f"\nVerified: {len(verified)}/{len(rows)}  -> {OUT}")
    if missed:
        print(f"Missed ({len(missed)}): {', '.join(missed)}")
        print("Fix slugs in seed_companies.csv or drop these companies.")


if __name__ == "__main__":
    main()
