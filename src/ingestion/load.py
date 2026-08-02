import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime

import psycopg
from dotenv import load_dotenv

from src.ingestion.adzuna_client import ADZUNA_ENDPOINT_URL
from src.ingestion.adzuna_client import fetch_latest_jobs as fetch_adzuna_jobs
from src.ingestion.hn_client import HNThread, find_hiring_threads, fetch_thread
from src.ingestion.remotive_client import (
    REMOTIVE_ENDPOINT_URL,
)
from src.ingestion.remotive_client import (
    fetch_latest_jobs as fetch_remotive_jobs,
)

load_dotenv()

logger = logging.getLogger(__name__)

HN_BACKFILL_SINCE = date(2023, 1, 1)
HN_BACKFILL_UNTIL = date(2023, 12, 31)

UPSERT_SQL = """
INSERT INTO raw_postings (source, external_id, raw_text, thread_month, posted_at)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (source, external_id) DO UPDATE
  SET raw_text   = EXCLUDED.raw_text,
      posted_at  = EXCLUDED.posted_at,
      updated_at = now()
  WHERE raw_postings.raw_text IS DISTINCT FROM EXCLUDED.raw_text
RETURNING (xmax = 0) AS inserted;
"""


@dataclass(frozen=True)
class LoadStats:
    inserted: int
    updated: int
    unchanged: int


def to_posted_at(created_at: str) -> datetime:
    dt = datetime.fromisoformat(created_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def to_thread_month(posted_at: datetime) -> date:
    return posted_at.date().replace(day=1)


Row = tuple[str, str, str, date, datetime]


def hnthread_to_rows(thread: HNThread) -> list[Row]:
    thread_month = to_thread_month(to_posted_at(thread.created_at))
    rows: list[Row] = []
    for comment in thread.comments:
        posted_at = to_posted_at(comment.created_at)
        rows.append(("hn", comment.id, comment.text, thread_month, posted_at))
    return rows


def fetch_hn_rows(since: date, until: date) -> list[Row]:
    threads_meta = find_hiring_threads(since=since, until=until)
    threads = [fetch_thread(story_id) for story_id, _ in threads_meta]
    return [row for thread in threads for row in hnthread_to_rows(thread)]


def remotive_to_rows(jobs: list[dict]) -> list[Row]:
    rows: list[Row] = []
    for job in jobs:
        posted_at = to_posted_at(job["publication_date"])
        thread_month = to_thread_month(posted_at)
        rows.append(("remotive", job["id"], json.dumps(job), thread_month, posted_at))
    return rows


def adzuna_to_rows(jobs: list[dict]) -> list[Row]:
    rows: list[Row] = []
    for job in jobs:
        posted_at = to_posted_at(job["created"])
        thread_month = to_thread_month(posted_at)
        rows.append(("adzuna", job["id"], json.dumps(job), thread_month, posted_at))
    return rows


def upsert_posting(conn, rows) -> LoadStats:
    inserted = updated = 0
    with conn.cursor() as cur:
        for row in rows:
            try:
                cur.execute(UPSERT_SQL, row)
                result = cur.fetchone()
            except psycopg.Error:
                logger.exception("upsert failed for %s/%s", row[0], row[1])
                continue
            if result is None:
                continue
            elif result[0]:
                inserted += 1
            else:
                updated += 1
    unchanged = len(rows) - inserted - updated
    return LoadStats(inserted, updated, unchanged)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    hn_posting_rows = fetch_hn_rows(HN_BACKFILL_SINCE, HN_BACKFILL_UNTIL)
    logger.info("Fetched %d postings from Hacker News.", len(hn_posting_rows))

    remotive_jobs = fetch_remotive_jobs(REMOTIVE_ENDPOINT_URL)
    remotive_posting_rows = remotive_to_rows(remotive_jobs)
    logger.info("Fetched %d postings from Remotive.", len(remotive_posting_rows))

    adzuna_jobs = fetch_adzuna_jobs(
        url=ADZUNA_ENDPOINT_URL, keywords="python developer", category="it-jobs", country="us"
    )
    adzuna_posting_rows = adzuna_to_rows(adzuna_jobs)
    logger.info("Fetched %d postings from Adzuna.", len(adzuna_posting_rows))

    db_url = os.environ["DATABASE_URL"]

    try:
        with psycopg.connect(db_url) as conn:
            logger.info("Ingesting data into raw_postings...")
            stats = upsert_posting(
                conn, hn_posting_rows + remotive_posting_rows + adzuna_posting_rows
            )

            logger.info(
                "Ingestion results — inserted: %d, updated: %d, unchanged: %d",
                stats.inserted,
                stats.updated,
                stats.unchanged,
            )
    except Exception:
        logger.exception("Ingestion failed")
        raise