"""
Sponsor Radar — Step 3a: embed jobs for semantic matching.

Embeds every UK job that doesn't have an embedding yet, using gte-small —
the same model Supabase Edge Functions run at request time for the CV,
so both sides live in the same vector space.

Run (in GitHub Actions after fetch_jobs.py):
    pip install sentence-transformers supabase
    python embed_jobs.py
"""

from __future__ import annotations

import os
import sys

from sentence_transformers import SentenceTransformer
from supabase import create_client

MODEL = "Supabase/gte-small"
BATCH = 64


def job_text(row: dict) -> str:
    """What we embed: title carries the most signal, so it leads and the
    description is truncated — embedding 15k chars of boilerplate about
    company culture dilutes the match."""
    return f"{row['title']}. {row['company']}. {(row['description'] or '')[:2000]}"


def main() -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    client = create_client(url, key)

    rows = (client.table("jobs")
            .select("id,title,company,description")
            .eq("is_uk", True)
            .is_("embedding", "null")
            .limit(2000)
            .execute()).data
    if not rows:
        print("Nothing to embed.")
        return

    print(f"Embedding {len(rows)} jobs with {MODEL}...")
    model = SentenceTransformer(MODEL)

    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        vectors = model.encode(
            [job_text(r) for r in chunk],
            normalize_embeddings=True,
        )
        for row, vec in zip(chunk, vectors):
            client.table("jobs").update(
                {"embedding": vec.tolist()}
            ).eq("id", row["id"]).execute()
        print(f"  {min(i + BATCH, len(rows))}/{len(rows)}")

    print("Done.")


if __name__ == "__main__":
    main()
