import os
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

import psycopg
from dotenv import load_dotenv
from pydantic_ai import Agent

from src.extraction.prompt import SYSTEM_PROMPT
from src.extraction.schema import DocType, PostingExtraction

load_dotenv()


class RawRow(NamedTuple):
    id: int
    source: str
    external_id: str
    raw_text: str


@dataclass(frozen=True)
class Outcome:
    status: Literal["ok", "invalid", "error"]
    model: str
    doc_type: DocType
    company: str | None = None
    errors: str | None = None


def pending(conn, sources=None, limit=None) -> list["RawRow"]:
    query = (
        "SELECT id, source, external_id, raw_text "
        "FROM raw_postings p "
        "WHERE NOT EXISTS ("
        "   SELECT 1 FROM extraction_runs r "
        "   WHERE r.raw_posting_id = p.id"
        ")"
    )
    if sources:
        query += " AND source = ANY(%s)"
    query += " ORDER BY id"
    if limit:
        query += " LIMIT %s"
    with conn.transaction():
        with conn.cursor() as cur:
            args: tuple[Any, ...] = ()
            if sources:
                args += (sources,)
            if limit:
                args += (limit,)

            cur.execute(query, args)
            return [RawRow(*row) for row in cur.fetchall()]


def build_agent(model: str, system_prompt: str,  retries=2) -> Agent[None, PostingExtraction]:
    return Agent(
        model=model,
        system_prompt=system_prompt,
        output_type=PostingExtraction,
        retries=retries
    )


if __name__ == "__main__":
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = pending(conn, sources=["hn"], limit=10)
        agent = build_agent(model="deepseek:deepseek-v4-flash", system_prompt=SYSTEM_PROMPT)
