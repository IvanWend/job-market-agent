import os
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from dotenv import load_dotenv

from src.ingestion.hn_client import HNThread, find_latest_hiring_thread, fetch_thread

UPSERT_SQL = """
INSERT INTO raw_postings (source, external_id, raw_text, thread_month) 
VALUES (%s, %s, %s, %s)
ON CONFLICT (external_id) DO UPDATE SET raw_text = EXCLUDED.raw_text, thread_month = EXCLUDED.thread_month
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


if __name__ == "__main__":
    story_id, _ = find_latest_hiring_thread()
    thread: HNThread = fetch_thread(story_id)
    thread_to_rows = thread_to_rows(thread)
    print(f"Fetched {len(thread_to_rows)} comments from thread {story_id}")
    print(f"First comment: {thread_to_rows[2]}")