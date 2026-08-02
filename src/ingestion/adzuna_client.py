import logging
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ADZUNA_ENDPOINT_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch_latest_jobs(
    url: str, keywords=None, category=None, max_pages=10, country="us", max_retries=3
) -> list[dict]:
    params = {
        "app_id": os.environ.get("ADZUNA_APP_ID"),
        "app_key": os.environ.get("ADZUNA_APP_KEY"),
        "content-type": "application/json",
        "results_per_page": 50,
    }

    if keywords:
        params["what"] = keywords
    if category:
        params["category"] = category

    all_jobs = []

    for page in range(1, max_pages + 1):
        page_url = url.format(country=country, page=page)

        for attempt in range(max_retries):
            try:
                resp = requests.get(page_url, params=params, timeout=10)
                resp.raise_for_status()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2**attempt
                logger.warning("Adzuna page %d failed (%s), retrying in %ds...", page, e, wait)
                time.sleep(wait)

        data = resp.json()
        results = data.get("results")
        if not results:
            break
        all_jobs.extend(results)

        time.sleep(1)

    return all_jobs


if __name__ == "__main__":
    job_objects = fetch_latest_jobs(
        url=ADZUNA_ENDPOINT_URL,
        keywords="python developer",
        category="it-jobs",
        max_pages=10,
        country="us",
    )
    print(f"Process complete. Gathered {len(job_objects)} total jobs.")
