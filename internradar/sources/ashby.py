"""Ashby: GET api.ashbyhq.com/posting-api/job-board/{board} (one request)."""

from __future__ import annotations

from datetime import date

from ..models import Posting, clean, is_internship, iso_to_date
from .base import expect_ok

NAME = "ashby"


def url(cfg: dict) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{cfg['board']}"


def parse(data: dict, cfg: dict, today: date) -> tuple[list[Posting], int]:
    jobs = data.get("jobs", [])
    out = []
    for j in jobs:
        if j.get("isListed") is False:
            continue
        title = clean(j.get("title"))
        if not is_internship(title, j.get("employmentType") == "Intern"):
            continue
        locations = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
        if j.get("workplaceType") == "Remote" and not any("remote" in (x or "").lower() for x in locations):
            locations.append("Remote")
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME, source_id=str(j["id"]),
            title=title,
            location="; ".join(clean(x) for x in locations if x),
            url=j.get("jobUrl") or "",
            posted_at=iso_to_date(j.get("publishedAt")),
        ))
    return out, len(jobs)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    return parse(expect_ok(client.fetch(url(cfg)), dict), cfg, today)
