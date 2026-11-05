"""Workday careers sites (e.g. NVIDIA). The listing is built by JavaScript, so String
renders it in a browser and returns Markdown, which is parsed here.
Only the first page of results (20 jobs) is returned; see README "Known gaps"."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote, urlsplit, urlunsplit

from ..models import Posting, clean, is_internship, relative_to_date
from .base import expect_ok

NAME = "workday"
JOB_RE = re.compile(r"###\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)\s]+)\)(?P<body>.*?)(?=###\s*\[|\Z)", re.S)
ID_RE = re.compile(r"_(?P<id>[A-Z]*R?-?\d+(?:-\d+)?)$")


def url(cfg: dict) -> str:
    return f"https://{cfg['host']}/en-US/{cfg['site']}?q={quote(cfg.get('query', 'intern'))}"


def _field(body: str, label: str) -> str:
    """Value on the first non-empty line after a label line like 'locations'."""
    m = re.search(rf"^\s*{label}\s*$\s*^\s*(\S.*?)\s*$", body, re.M | re.I)
    return clean(m.group(1)) if m else ""


def parse(markdown: str, cfg: dict, today: date) -> tuple[list[Posting], int]:
    out, seen = [], 0
    for m in JOB_RE.finditer(markdown):
        seen += 1
        title = clean(m.group("title"))
        if not is_internship(title):
            continue
        parts = urlsplit(m.group("url"))
        job_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))  # drop ?q=
        id_match = ID_RE.search(parts.path)
        posted_text = _field(m.group("body"), "posted on")
        out.append(Posting(
            company_id=cfg["id"], company=cfg["name"], source=NAME,
            source_id=id_match.group("id") if id_match else parts.path,
            title=title,
            location=_field(m.group("body"), "locations"),
            url=job_url,
            posted_at=relative_to_date(posted_text, today),
            posted_text=posted_text.replace("Posted ", "").lower(),
        ))
    return out, seen


def fetch(cfg: dict, client, today: date) -> tuple[list[Posting], int]:
    result = client.fetch(url(cfg), executeJS=True, waitUntil="networkidle2",
                          format="markdown", mainContentOnly=True)
    return parse(expect_ok(result, str), cfg, today)
