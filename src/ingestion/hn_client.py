import requests

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"

def find_latest_hiring_thread():
    params = {
        "query": "who is hiring",
        "tags": "story,author_whoishiring",
        "hitsPerPage": 10,
    }
    resp = requests.get(ALGOLIA_URL, params=params, timeout=10)
    resp.raise_for_status()

    hits = resp.json()["hits"]
    for hit in hits:
        if "who is hiring" in hit["title"].lower():
            return hit["objectID"], hit["title"]


    raise RuntimeError(
        f"No 'Who is hiring' thread found in {len(hits)} newest whoishiring posts"
    )

if __name__ == "__main__":
    story_id, title = find_latest_hiring_thread()
    print(f"story_id: {story_id} ({type(story_id).__name__})")
    print(f"title:    {title}")
    print(f"verify:   https://news.ycombinator.com/item?id={story_id}")

