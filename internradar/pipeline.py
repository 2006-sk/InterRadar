"""One scrape run: fetch every company, normalise, filter, store."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from . import db
from .http import FetchError
from .models import Posting
from .sources import SOURCES


@dataclass
class CompanyResult:
    company_id: str
    name: str
    ok: bool
    jobs_seen: int = 0
    internships: int = 0
    new: int = 0
    closed: int = 0
    requests: int = 0
    duration_ms: int = 0
    error: str | None = None


@dataclass
class RunSummary:
    run_id: int
    results: list[CompanyResult] = field(default_factory=list)
    aborted: str | None = None

    @property
    def ok(self) -> int:
        return sum(r.ok for r in self.results)

    @property
    def failed(self) -> int:
        return sum(not r.ok for r in self.results)

    @property
    def new(self) -> int:
        return sum(r.new for r in self.results)


def load_companies(path: str | Path) -> list[dict]:
    companies = json.loads(Path(path).read_text())
    for c in companies:
        missing = {"id", "name", "source"} - c.keys()
        if missing:
            raise ValueError(f"{path}: company {c} is missing {sorted(missing)}")
        if c["source"] not in SOURCES:
            raise ValueError(f"{path}: unknown source {c['source']!r} for {c['id']} (known: {sorted(SOURCES)})")
    return companies


def dedupe(postings: list[Posting]) -> list[Posting]:
    """Drop repeats of the same job inside one fetch (e.g. overlapping pages)."""
    seen: dict[str, Posting] = {}
    for p in postings:
        seen.setdefault(p.key, p)
    return list(seen.values())


def scrape(conn: sqlite3.Connection, companies: list[dict], client, today: date | None = None,
           log: Callable[[str], None] = print) -> RunSummary:
    today = today or date.today()
    summary = RunSummary(run_id=db.start_run(conn, client.name))
    for i, cfg in enumerate(companies, 1):
        if summary.aborted:
            res = CompanyResult(cfg["id"], cfg["name"], ok=False, error=f"skipped: {summary.aborted}")
        else:
            res = _scrape_one(conn, summary.run_id, cfg, client, today, summary)
        summary.results.append(res)
        db.log_fetch(conn, summary.run_id, res.company_id, ok=res.ok, jobs_seen=res.jobs_seen,
                     internships=res.internships, new=res.new, closed=res.closed,
                     requests=res.requests, duration_ms=res.duration_ms, error=res.error)
        status = (f"{res.internships:3} internships ({res.new} new, {res.closed} closed) from {res.jobs_seen} jobs"
                  if res.ok else f"FAILED: {res.error}")
        log(f"[{i:2}/{len(companies)}] {cfg['name']:<14} {status}")
    db.finish_run(conn, summary.run_id, companies_ok=summary.ok, companies_failed=summary.failed,
                  postings_seen=sum(r.internships for r in summary.results), postings_new=summary.new,
                  postings_closed=sum(r.closed for r in summary.results), requests=client.requests_made)
    return summary


def _scrape_one(conn, run_id, cfg, client, today, summary) -> CompanyResult:
    res = CompanyResult(cfg["id"], cfg["name"], ok=False)
    before, t0 = client.requests_made, time.monotonic()
    try:
        postings, seen = SOURCES[cfg["source"]].fetch(cfg, client, today)
    except FetchError as e:
        res.error = str(e)
        if e.fatal:
            summary.aborted = str(e)
    except Exception as e:  # a parser bug in one source shouldn't sink the whole run
        res.error = f"{type(e).__name__}: {e}"
    else:
        postings = dedupe(postings)
        # Only reached when every page fetched, so it's safe to mark missing postings closed.
        res.new, res.closed = db.save_company(conn, run_id, cfg["id"], postings)
        res.ok, res.jobs_seen, res.internships = True, seen, len(postings)
    res.requests = client.requests_made - before
    res.duration_ms = int((time.monotonic() - t0) * 1000)
    return res
