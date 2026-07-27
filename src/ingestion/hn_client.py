from dataclasses import dataclass

import requests

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items"


@dataclass(frozen=True)
class HNComment:
    """One top-level comment on a hiring thread — i.e. one job posting."""

    id: str  # comment id as TEXT; becomes raw_postings.external_id
    text: str  # HTML, verbatim — stripping is extraction's job, not ingestion's


@dataclass(frozen=True)
class HNThread:
    """A monthly "Who is hiring" thread and its postings."""

    story_id: str
    title: str
    created_at: str  # raw ISO-8601 from the API; load.py derives thread_month from it
    comments: list[HNComment]


def find_latest_hiring_thread() -> tuple[str, str]:
    params: dict[str, str | int] = {
        "query": "who is hiring",
        "tags": "story,author_whoishiring",
        "hitsPerPage": 10,
    }
    resp = requests.get(ALGOLIA_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()

    hits = resp.json()["hits"]
    for hit in hits:
        if "who is hiring" in hit["title"].lower():
            return hit["objectID"], hit["title"]

    raise RuntimeError(f"No 'Who is hiring' thread found in {len(hits)} newest whoishiring posts")


def fetch_thread(story_id: str) -> HNThread:
    """Fetch a thread and its top-level comments in a single request.

    /items/ returns the whole comment tree, so `children` is exactly the top-level
    list: no pagination, no client-side depth filter, and the story's own metadata
    comes back in the same payload.
    """
    resp = requests.get(f"{ALGOLIA_ITEM_URL}/{story_id}", timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    comments: list[HNComment] = []
    for child in payload["children"]:
        # Deleted comments carry a null `text`; blank ones are not postings either.
        text = (child.get("text") or "").strip()
        if not text:
            continue
        comments.append(HNComment(id=str(child["id"]), text=text))

    return HNThread(
        story_id=story_id,
        title=payload["title"],
        created_at=payload["created_at"],
        comments=comments,
    )


if __name__ == "__main__":
    # fetch_thread reads the title itself, so the one from search is redundant here.
    story_id, _ = find_latest_hiring_thread()
    thread = fetch_thread(story_id)
    print(f"thread:   {thread.title}")
    print(f"story_id: {thread.story_id}")
    print(f"posted:   {thread.created_at}")
    print(f"comments: {len(thread.comments)}")
    print(f"verify:   https://news.ycombinator.com/item?id={thread.story_id}")
