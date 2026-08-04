import json
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

HN_PATH = "evals/candidates_hn.json"
ADZUNA_PATH = "evals/candidates_adzuna.json"
REMOTIVE_PATH = "evals/candidates_remotive.json"

CANDIDATES_PER_SOURCE = 10


def extract_ids(path: str, source: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as f:
        candidates = json.load(f)
    return [(source, item["external_id"]) for item in candidates[:CANDIDATES_PER_SOURCE]]


if __name__ == "__main__":
    all_ids = (
        extract_ids(HN_PATH, "hn")
        + extract_ids(ADZUNA_PATH, "adzuna")
        + extract_ids(REMOTIVE_PATH, "remotive")
    )

    rows = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        for source, external_id in all_ids:
            cur.execute(
                "SELECT source, external_id, raw_text, posted_at FROM raw_postings "
                "WHERE source = %s AND external_id = %s",
                (source, external_id),
            )
            row = cur.fetchone()
            if row is None:
                continue
            rows.append(
                {
                    "source": row[0],
                    "external_id": row[1],
                    "raw_text": row[2],
                    "posted_at": row[3].isoformat() if row[3] else None,
                }
            )

    output_file = "evals/gold_30_candidates.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} rows to {output_file}")
