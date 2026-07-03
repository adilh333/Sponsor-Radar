"""
Sponsor Radar — Step 1: Ingest the UK Register of Licensed Sponsors.

Downloads the latest Worker & Temporary Worker register from gov.uk,
cleans it, normalises company names for matching, dedupes routes into
one row per company, and writes clean output (CSV + optional Supabase).

Run daily via GitHub Actions or locally:
    pip install requests beautifulsoup4 pandas
    python ingest_sponsor_register.py
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REGISTER_PAGE = (
    "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
)
OUT_DIR = Path("data")

# Routes we care about for graduate job seekers. Everything else
# (Creative Worker, Ministers of Religion, etc.) is noise for our users.
RELEVANT_ROUTES = {
    "Skilled Worker",
    "Scale-up",
}

# --- Company-name normalisation -------------------------------------------
# The register's only join key to job postings is the company name, and both
# sides write names differently ("Monzo Bank Ltd" vs "Monzo"). We keep the
# original name for display and build a normalised key for matching.

LEGAL_SUFFIXES = re.compile(
    r"\b(limited|ltd\.?|llp|plc|inc\.?|llc|l\.l\.c|co\.?|company|"
    r"corporation|corp\.?|holdings?|group|uk|gb|\(uk\)|\(gb\))\b",
    re.IGNORECASE,
)
TRADING_AS = re.compile(r"\b(t/?as?|trading as|t/a)\b.*$", re.IGNORECASE)
NON_ALNUM = re.compile(r"[^a-z0-9 ]")
MULTISPACE = re.compile(r"\s+")


def normalise_name(raw: str) -> str:
    """Produce a stable matching key from a messy register name."""
    s = raw.strip().lower()
    s = TRADING_AS.sub("", s)          # drop "T/A Some Shop Name" tails
    s = LEGAL_SUFFIXES.sub("", s)      # drop Ltd/PLC/LLP/etc.
    s = NON_ALNUM.sub(" ", s)          # punctuation -> space
    s = MULTISPACE.sub(" ", s).strip()
    return s


def extract_trading_name(raw: str) -> str | None:
    """If the entry has a T/A trading name, capture it — job boards often
    post under the trading name, not the legal name."""
    m = re.search(r"\b(?:t/?as?|trading as|t/a)\b\s*(.+)$", raw, re.IGNORECASE)
    if m:
        name = m.group(1).strip(" .,")
        return name or None
    return None


def clean_town(raw: str) -> str:
    s = MULTISPACE.sub(" ", raw.strip().strip(",").strip()).title()
    # Common junk values seen in the real file
    if s.lower() in {"", "choose county", "select a state", "state/province",
                     "united kingdom", "uk", "england", "scotland", "wales"}:
        return ""
    return s


def parse_rating(type_and_rating: str) -> tuple[str, str]:
    """'Worker (A rating)' -> ('Worker', 'A'). Handles B ratings and
    provisional statuses."""
    kind = type_and_rating.split("(")[0].strip()
    m = re.search(r"\(([^)]*)\)", type_and_rating)
    detail = (m.group(1) if m else "").strip()
    if re.search(r"\bA rating\b", detail, re.IGNORECASE):
        rating = "A"
    elif re.search(r"\bB rating\b", detail, re.IGNORECASE):
        rating = "B"
    else:
        rating = detail or "Unknown"   # e.g. "UK Expansion Worker: Provisional"
    return kind, rating


# --- Download ---------------------------------------------------------------

def find_latest_csv_url() -> str:
    """The CSV filename changes every day, so scrape the publication page
    for the current attachment link."""
    resp = requests.get(REGISTER_PAGE, timeout=30,
                        headers={"User-Agent": "SponsorRadar/0.1"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.select("a[href]"):
        href = a["href"]
        if href.endswith(".csv") and "assets.publishing.service.gov.uk" in href:
            return href
    raise RuntimeError("Could not find CSV link on the register page")


def download_register(dest: Path) -> Path:
    url = find_latest_csv_url()
    print(f"Downloading: {url}")
    resp = requests.get(url, timeout=120,
                        headers={"User-Agent": "SponsorRadar/0.1"})
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"Saved {len(resp.content)/1e6:.1f} MB -> {dest}")
    return dest


# --- Transform --------------------------------------------------------------

def process(raw_csv: Path, out_csv: Path) -> dict:
    """Clean and aggregate: one output row per company, with its routes
    collected into a list. Returns summary stats."""
    companies: dict[str, dict] = {}
    total_rows = 0

    with raw_csv.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1
            raw_name = (row.get("Organisation Name") or "").strip()
            if not raw_name:
                continue
            route = (row.get("Route") or "").strip()
            kind, rating = parse_rating(row.get("Type & Rating") or "")

            key = normalise_name(raw_name)
            if not key:
                continue

            entry = companies.setdefault(key, {
                "name": raw_name,
                "normalised_name": key,
                "trading_name": extract_trading_name(raw_name),
                "town": clean_town(row.get("Town/City") or ""),
                "county": clean_town(row.get("County") or ""),
                "routes": set(),
                "ratings": set(),
                "has_skilled_worker": False,
            })
            entry["routes"].add(route)
            entry["ratings"].add(rating)
            if route in RELEVANT_ROUTES and rating == "A":
                entry["has_skilled_worker"] = True

    # Write clean output
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name", "normalised_name", "trading_name", "town", "county",
            "routes", "ratings", "skilled_worker_a_rated", "register_date",
        ])
        today = date.today().isoformat()
        for entry in sorted(companies.values(), key=lambda e: e["normalised_name"]):
            writer.writerow([
                entry["name"],
                entry["normalised_name"],
                entry["trading_name"] or "",
                entry["town"],
                entry["county"],
                "|".join(sorted(entry["routes"])),
                "|".join(sorted(entry["ratings"])),
                entry["has_skilled_worker"],
                today,
            ])

    stats = {
        "raw_rows": total_rows,
        "unique_companies": len(companies),
        "skilled_worker_a_rated": sum(
            1 for e in companies.values() if e["has_skilled_worker"]
        ),
    }
    return stats


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    raw = OUT_DIR / "register_raw.csv"
    clean = OUT_DIR / "sponsors_clean.csv"

    if "--skip-download" not in sys.argv:
        download_register(raw)

    stats = process(raw, clean)
    print(f"Raw rows:                 {stats['raw_rows']:,}")
    print(f"Unique companies:         {stats['unique_companies']:,}")
    print(f"Skilled Worker (A-rated): {stats['skilled_worker_a_rated']:,}")
    print(f"Clean output -> {clean}")


if __name__ == "__main__":
    main()

