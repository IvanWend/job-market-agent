import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import NamedTuple

import psycopg
from dotenv import load_dotenv

from src.ingestion.hn_client import HNThread, fetch_thread, find_latest_hiring_thread
from src.ingestion.remotive_client import REMOTIVE_ENDPOINT_URL
from src.ingestion.remotive_client import fetch_latest_jobs as fetch_remotive_jobs
from src.ingestion.retention import WINDOW_DAYS, window_cutoff
from src.ingestion.web3_client import WEB3_ENDPOINT_URL
from src.ingestion.web3_client import fetch_latest_jobs as fetch_web3_jobs

load_dotenv()

logger = logging.getLogger(__name__)

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


# A tuple so psycopg can pass it straight to UPSERT_SQL as parameters; named so
# the pipeline can read row.posted_at instead of row[4]. Field order is the
# INSERT column order and must stay that way.
class Row(NamedTuple):
    source: str
    external_id: str
    raw_text: str
    thread_month: date | None
    posted_at: datetime


@dataclass(frozen=True)
class LoadStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0

    def __add__(self, other: "LoadStats") -> "LoadStats":
        return LoadStats(
            self.inserted + other.inserted,
            self.updated + other.updated,
            self.unchanged + other.unchanged,
            self.failed + other.failed,
        )


def to_posted_at(created_at: str) -> datetime:
    dt = datetime.fromisoformat(created_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def to_thread_month(posted_at: datetime) -> date:
    return posted_at.date().replace(day=1)


def hnthread_to_rows(thread: HNThread) -> list[Row]:
    thread_month = to_thread_month(to_posted_at(thread.created_at))
    rows: list[Row] = []
    for comment in thread.comments:
        posted_at = to_posted_at(comment.created_at)
        rows.append(Row("hn", comment.id, comment.text, thread_month, posted_at))
    return rows


def remotive_to_rows(jobs: list[dict]) -> list[Row]:
    rows: list[Row] = []
    for job in jobs:
        posted_at = to_posted_at(job["publication_date"])
        thread_month = to_thread_month(posted_at)
        rows.append(Row("remotive", str(job["id"]), json.dumps(job), thread_month, posted_at))
    return rows


def web3_to_rows(jobs: list[dict]) -> list[Row]:
    rows: list[Row] = []
    for job in jobs:
        # `date` is RFC 2822 ("Mon, 10 Aug 2026 22:04:14 +0100"), which
        # fromisoformat cannot read; date_epoch carries the same instant.
        posted_at = datetime.fromtimestamp(int(job["date_epoch"]), tz=UTC)
        thread_month = to_thread_month(posted_at)
        rows.append(Row("web3", str(job["id"]), json.dumps(job), thread_month, posted_at))
    return rows


def fetch_hn_rows() -> list[Row]:
    story_id, _ = find_latest_hiring_thread()
    return hnthread_to_rows(fetch_thread(story_id))


def fetch_remotive_rows() -> list[Row]:
    return remotive_to_rows(fetch_remotive_jobs(REMOTIVE_ENDPOINT_URL))


def fetch_web3_rows() -> list[Row]:
    return web3_to_rows(fetch_web3_jobs(WEB3_ENDPOINT_URL, os.getenv("WEB3_API_KEY")))


# One entry per source. Each fetcher owns exactly one board, so a board that is
# down, rate-limited or has changed shape costs its own rows and nothing else.
SOURCES: dict[str, Callable[[], list[Row]]] = {
    "hn": fetch_hn_rows,
    "remotive": fetch_remotive_rows,
    "web3": fetch_web3_rows,
}


def within_window(rows: list[Row]) -> list[Row]:
    cutoff = window_cutoff()
    return [row for row in rows if row.posted_at >= cutoff]


def upsert_posting(conn, rows) -> LoadStats:
    inserted = updated = failed = 0
    # The outer block is the real transaction, so the source lands atomically
    # and conn.transaction() inside the loop opens a savepoint rather than
    # committing every row on its own.
    with conn.transaction(), conn.cursor() as cur:
        for row in rows:
            try:
                # A failed statement aborts the whole transaction in psycopg;
                # the savepoint keeps one bad row from taking the rest with it.
                with conn.transaction():
                    cur.execute(UPSERT_SQL, row)
                    result = cur.fetchone()
            except psycopg.Error:
                logger.exception("upsert failed for %s/%s", row.source, row.external_id)
                failed += 1
                continue
            if result is None:
                continue
            elif result[0]:
                inserted += 1
            else:
                updated += 1
    unchanged = len(rows) - inserted - updated - failed
    return LoadStats(inserted, updated, unchanged, failed)


def load_source(conn, name: str, fetch: Callable[[], list[Row]]) -> LoadStats:
    rows = fetch()
    fresh = within_window(rows)
    logger.info(
        "%s: fetched %d postings, %d within %d days.", name, len(rows), len(fresh), WINDOW_DAYS
    )

    stats = upsert_posting(conn, fresh)
    logger.info(
        "%s: inserted %d, updated %d, unchanged %d, failed %d.",
        name,
        stats.inserted,
        stats.updated,
        stats.unchanged,
        stats.failed,
    )
    return stats


def load_all(conn) -> LoadStats:
    total = LoadStats()
    succeeded = 0
    for name, fetch in SOURCES.items():
        try:
            total += load_source(conn, name, fetch)
            succeeded += 1
        except Exception:
            logger.exception("%s: source failed, continuing with the rest", name)
            conn.rollback()

    if succeeded == 0:
        raise RuntimeError(f"all {len(SOURCES)} sources failed — see the logged tracebacks")
    return total


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        stats = load_all(conn)
        logger.info(
            "Total — inserted: %d, updated: %d, unchanged: %d, failed: %d",
            stats.inserted,
            stats.updated,
            stats.unchanged,
            stats.failed,
        )
