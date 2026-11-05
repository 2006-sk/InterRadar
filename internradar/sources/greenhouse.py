"""Greenhouse job boards: GET boards-api.greenhouse.io/v1/boards/{board}/jobs (one request)."""

from __future__ import annotations

from datetime import date

from ..models import Posting, clean, is_internship, iso_to_date
from .base import expect_ok

NAME = "greenhouse"


def url(cfg: dict) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{cfg['board']}/jobs"


def parse(data: dict, cfg: dict, today: date) -> tuple[list[Posting], int]:
    jobs = data.get("jobs", [])
    out = []
    for j in jobs:
        title = clean(j.get("title"))
        if not is_internship(title):
            continue
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME, source_id=str(j["id"]),
            title=title,
            location=clean((j.get("location") or {}).get("name")),
            url=j.get("absolute_url") or "",
            posted_at=iso_to_date(j.get("first_published") or j.get("updated_at")),
        ))
    return out, len(jobs)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    return parse(expect_ok(client.fetch(url(cfg)), dict), cfg, today)
