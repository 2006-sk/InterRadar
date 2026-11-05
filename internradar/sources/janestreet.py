"""Jane Street: GET www.janestreet.com/jobs/main.json (one request).
Internships are marked by the `availability` field, not the title, and there is no posted date."""

from __future__ import annotations

from datetime import date

from ..models import Posting, clean
from .base import expect_ok

NAME = "janestreet"
CITIES = {"NYC": "New York", "LDN": "London", "HKG": "Hong Kong", "SGP": "Singapore",
          "AMS": "Amsterdam", "CHI": "Chicago", "ATX": "Austin"}


def url(cfg: dict) -> str:
    return "https://www.janestreet.com/jobs/main.json"


def parse(data: list, cfg: dict, today: date) -> tuple[list[Posting], int]:
    out = []
    for j in data:
        availability = clean(j.get("availability"))
        if "intern" not in availability.lower():
            continue
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME, source_id=str(j["id"]),
            title=f"{clean(j.get('position'))} ({availability})",
            location=CITIES.get(j.get("city"), j.get("city") or ""),
            url=f"https://www.janestreet.com/join-jane-street/position/{j['id']}/",
            posted_at=None,
        ))
    return out, len(data)


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    return parse(expect_ok(client.fetch(url(cfg)), list), cfg, today)
