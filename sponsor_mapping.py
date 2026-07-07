"""
Sponsor Radar — verified sponsor mapping.

Fuzzy matching proposes register entries; you approve them. This exists
because trigram similarity produced at least one confident false positive
(Encord -> "Encortec Limited"), and a wrong "licensed sponsor" claim is the
worst error this product can make.

Two modes:

1. Propose — writes sponsor_mapping_review.csv with the top-3 register
   candidates per seed company:
       python sponsor_mapping.py propose

2. Apply — after you edit the CSV (put 1/2/3 in the `choice` column to pick
   a candidate, 0 to reject all), writes approved rows to sponsor_overrides
   and re-points existing jobs:
       python sponsor_mapping.py apply

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY env vars.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

from supabase import create_client

VERIFIED = Path("data/verified_companies.csv")
REVIEW = Path("data/sponsor_mapping_review.csv")


def client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    return create_client(url, key)


def propose() -> None:
    sb = client()
    with VERIFIED.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    REVIEW.parent.mkdir(exist_ok=True)
    with REVIEW.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", "slug", "choice",
                    "cand1_id", "cand1_name", "cand1_town", "cand1_score",
                    "cand2_id", "cand2_name", "cand2_town", "cand2_score",
                    "cand3_id", "cand3_name", "cand3_town", "cand3_score"])
        for c in companies:
            cands = sb.rpc("propose_sponsors",
                           {"company_name": c["company"], "k": 3}).execute().data
            row = [c["company"], c["slug"], ""]
            for cand in cands:
                row += [cand["sponsor_id"], cand["register_name"],
                        cand["town"] or "", f"{cand['score']:.2f}"]
            row += [""] * (15 - len(row))
            w.writerow(row)
            top = cands[0] if cands else None
            flag = "" if top and top["score"] >= 0.75 else "  <-- REVIEW CAREFULLY"
            print(f"{c['company']:28} -> {top['register_name'] if top else 'NO CANDIDATE':45}"
                  f" ({top['score']:.2f}){flag}" if top else f"{c['company']:28} -> NO CANDIDATE")

    print(f"\nWrote {REVIEW}.")
    print("Open it, set `choice` to 1/2/3 for the correct candidate "
          "(0 if none are right), then run: python sponsor_mapping.py apply")


def apply() -> None:
    sb = client()
    approved, rejected, skipped = 0, 0, 0
    with REVIEW.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            choice = row["choice"].strip()
            if choice not in {"1", "2", "3"}:
                rejected += choice == "0"
                skipped += choice not in {"0"}
                continue
            sid = row[f"cand{choice}_id"]
            name = row[f"cand{choice}_name"]
            if not sid:
                continue
            sb.table("sponsor_overrides").upsert({
                "company_slug": row["slug"],
                "company_name": row["company"],
                "sponsor_id": int(sid),
                "note": f"approved candidate {choice}: {name}",
            }).execute()
            approved += 1

    repointed = sb.rpc("apply_overrides_to_jobs").execute().data
    print(f"Approved: {approved} | rejected (0): {rejected} | "
          f"left blank: {skipped}")
    print(f"Existing jobs re-pointed to verified sponsors: {repointed}")
    if rejected:
        print("Rejected companies keep NO sponsor link — their jobs will "
              "drop out of results until mapped, which is the safe default.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "propose":
        propose()
    elif mode == "apply":
        apply()
    else:
        sys.exit("Usage: python sponsor_mapping.py [propose|apply]")
