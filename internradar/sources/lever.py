"""Lever: GET api.lever.co/v0/postings/{board}?mode=json (one request)."""

from __future__ import annotations

from datetime import date

from ..models import Posting, clean, epoch_ms_to_date, is_internship
from .base import expect_ok

NAME = "lever"


def url(cfg: dict) -> str:
    return f"https://api.lever.co/v0/postings/{cfg['board']}?mode=json"


def parse(data: list, cfg: dict, today: date) -> tuple[list[Posting], int]:
    out = []
    for j in data:
        cats = j.get("categories") or {}
        title = clean(j.get("text"))
        if not is_internship(title, "intern" in (cats.get("commitment") or "").lower()):
            continue
        locations = cats.get("allLocations") or [cats.get("location")]
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME, source_id=str(j["id"]),
            title=title,
            location="; ".join(clean(x) for x in locations if x),
            url=j.get("hostedUrl") or "",
            posted_at=epoch_ms_to_date(j.get("createdAt")),
        ))
    return out, len(data)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    return parse(expect_ok(client.fetch(url(cfg)), list), cfg, today)
