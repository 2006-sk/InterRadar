"""SmartRecruiters: GET api.smartrecruiters.com/v1/companies/{board}/postings?q=...
Paginated (100 per page). The `q` search is fuzzy, so titles are filtered again here."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from ..models import Posting, clean, is_internship, iso_to_date
from .base import expect_ok

NAME = "smartrecruiters"
PAGE = 100


def url(cfg: dict, offset: int = 0) -> str:
    q = quote(cfg.get("query", "intern"))
    return f"https://api.smartrecruiters.com/v1/companies/{cfg['board']}/postings?q={q}&limit={PAGE}&offset={offset}"


def parse(data: dict, cfg: dict, today: date) -> tuple[list[Posting], int]:
    jobs = data.get("content", [])
    out = []
    for j in jobs:
        title = clean(j.get("name"))
        employment = ((j.get("typeOfEmployment") or {}).get("id") or "").lower()
        if not is_internship(title, "intern" in employment):
            continue
        loc = j.get("location") or {}
        location = clean(loc.get("fullLocation")) or ", ".join(
            x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
        if loc.get("remote"):
            location = f"{location} (Remote)" if location else "Remote"
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME, source_id=str(j["id"]),
            title=title, location=location,
            url=f"https://jobs.smartrecruiters.com/{cfg['board']}/{j['id']}",
            posted_at=iso_to_date(j.get("releasedDate")),
        ))
    return out, len(jobs)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    postings, seen, offset = [], 0, 0
    for _ in range(cfg.get("max_pages", 3)):
        data = expect_ok(client.fetch(url(cfg, offset)), dict)
        page, n = parse(data, cfg, today)
        postings += page
        seen += n
        offset += PAGE
        if n == 0 or offset >= data.get("totalFound", 0):
            break
    return postings, seen
