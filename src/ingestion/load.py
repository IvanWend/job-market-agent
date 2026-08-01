import os
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from dotenv import load_dotenv

from src.ingestion.hn_client import HNThread, find_latest_hiring_thread, fetch_thread

load_dotenv()

UPSERT_SQL = """
INSERT INTO raw_postings (source, external_id, raw_text, thread_month)
VALUES (%s, %s, %s, %s)
ON CONFLICT (source, external_id) DO UPDATE
  SET raw_text   = EXCLUDED.raw_text,
      updated_at = now()
  WHERE raw_postings.raw_text IS DISTINCT FROM EXCLUDED.raw_text
RETURNING (xmax = 0) AS inserted;
"""


@dataclass(frozen=True)
class LoadStats:
    inserted: int
    updated: int
    unchanged: int


def to_thread_month(created_at: str) -> date:
    dt = datetime.fromisoformat(created_at)
    return dt.date().replace(day=1)


def thread_to_rows(thread: HNThread) -> list[tuple[str, str, str, date]]:
    thread_month = to_thread_month(thread.created_at)
    rows: list[tuple[str, str, str, date]] = []
    for comment in thread.comments:
        rows.append(("hn", comment.id, comment.text, thread_month))
    return rows


def upsert_posting(conn, rows) -> LoadStats:
    inserted = updated = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(UPSERT_SQL, row)
            result = cur.fetchone()
            if result is None:
                continue
            elif result[0]:
                inserted += 1
            else:
                updated += 1
    unchanged = len(rows) - inserted - updated
    return LoadStats(inserted, updated, unchanged)


if __name__ == "__main__":
    story_id, _ = find_latest_hiring_thread()
    thread: HNThread = fetch_thread(story_id)

    posting_rows = thread_to_rows(thread)
    print(f"Fetched {len(posting_rows)} postings.")

    db_url = os.environ.get("DATABASE_URL")

    try:
        with psycopg.connect(db_url) as conn:
            print("Ingesting data into raw_postings...")
            stats = upsert_posting(conn, posting_rows)

            print("\n--- Ingestion Results ---")
            print(f"Inserted: {stats.inserted}")
            print(f"Updated:  {stats.updated}")
            print(f"Unchanged: {stats.unchanged}")
    except Exception as e:
        print(f"Ingestion failed: {e}")
        raise
