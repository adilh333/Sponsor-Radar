"""
Sponsor Radar — upload the cleaned register to Supabase.

Usage:
    pip install supabase
    export SUPABASE_URL=https://<project>.supabase.co
    export SUPABASE_SERVICE_KEY=<service-role key, never the anon key here>
    python upload_to_supabase.py
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import date
from pathlib import Path

from supabase import create_client

CLEAN_CSV = Path("data/sponsors_clean.csv")
BATCH = 500


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    client = create_client(url, key)
    today = date.today().isoformat()

    rows = []
    with CLEAN_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "name": r["name"],
                "normalised_name": r["normalised_name"],
                "trading_name": r["trading_name"] or None,
                "town": r["town"] or None,
                "county": r["county"] or None,
                "routes": r["routes"].split("|") if r["routes"] else [],
                "ratings": r["ratings"].split("|") if r["ratings"] else [],
                "skilled_worker_a_rated": r["skilled_worker_a_rated"] == "True",
                "last_seen": today,
            })

    print(f"Upserting {len(rows):,} sponsors in batches of {BATCH}...")
    for i in range(0, len(rows), BATCH):
        client.table("sponsors").upsert(
            rows[i:i + BATCH],
            on_conflict="normalised_name",
        ).execute()
        print(f"  {min(i + BATCH, len(rows)):,}/{len(rows):,}")

    print("Done. Rows not seen today keep an older last_seen -> treated "
          "as inactive by the active_sponsors view.")


if __name__ == "__main__":
    main()

