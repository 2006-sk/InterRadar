"""Amazon: GET www.amazon.jobs/en/search.json?base_query=intern (paginated, 100 per page)."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from ..models import Posting, clean, is_internship, text_date_to_date
from .base import expect_ok

NAME = "amazon"
PAGE = 100


def url(cfg: dict, offset: int = 0) -> str:
    q = quote(cfg.get("query", "intern"))
    return (f"https://www.amazon.jobs/en/search.json?base_query={q}"
            f"&result_limit={PAGE}&offset={offset}&sort=recent")


def parse(data: dict, cfg: dict, today: date) -> tuple[list[Posting], int]:
    jobs = data.get("jobs", [])
    out = []
    for j in jobs:
        title = clean(j.get("title"))
        if not is_internship(title):
            continue
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME,
            source_id=str(j.get("id_icims") or j.get("id")),
            title=title,
            location=clean(j.get("normalized_location") or j.get("location")),
            url="https://www.amazon.jobs" + (j.get("job_path") or ""),
            posted_at=text_date_to_date(j.get("posted_date")),
        ))
    return out, len(jobs)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    postings, seen, offset = [], 0, 0
    for _ in range(cfg.get("max_pages", 5)):
        data = expect_ok(client.fetch(url(cfg, offset)), dict)
        page, n = parse(data, cfg, today)
        postings += page
        seen += n
        offset += PAGE
        if n == 0 or offset >= data.get("hits", 0):
            break
    return postings, seen
