"""SQLite storage: de-duplicates postings across runs and tracks new / closed ones.

Each scrape is a row in `runs`. A posting is identified by `key`
(company id + the source's own job id), so seeing it again just bumps
`last_seen_run`. A posting is "new" if `first_seen_run` is the latest run, and
"closed" when a company was fetched successfully but the posting was missing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Posting

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    transport        TEXT,
    companies_ok     INTEGER NOT NULL DEFAULT 0,
    companies_failed INTEGER NOT NULL DEFAULT 0,
    postings_seen    INTEGER NOT NULL DEFAULT 0,
    postings_new     INTEGER NOT NULL DEFAULT 0,
    postings_closed  INTEGER NOT NULL DEFAULT 0,
    requests         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS postings (
    key            TEXT PRIMARY KEY,
    company_id     TEXT NOT NULL,
    company        TEXT NOT NULL,
    source         TEXT NOT NULL,
    source_id      TEXT NOT NULL,
    title          TEXT NOT NULL,
    location       TEXT NOT NULL DEFAULT '',
    url            TEXT NOT NULL,
    posted_at      TEXT,
    posted_text    TEXT NOT NULL DEFAULT '',
    is_tech        INTEGER NOT NULL DEFAULT 0,
    first_seen_run INTEGER NOT NULL REFERENCES runs(id),
    last_seen_run  INTEGER NOT NULL REFERENCES runs(id),
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    active         INTEGER NOT NULL DEFAULT 1,
    closed_run     INTEGER REFERENCES runs(id)
);
CREATE INDEX IF NOT EXISTS idx_postings_company ON postings(company_id, active);
CREATE INDEX IF NOT EXISTS idx_postings_first_seen ON postings(first_seen_run);
CREATE TABLE IF NOT EXISTS fetch_log (
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    company_id  TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    jobs_seen   INTEGER NOT NULL DEFAULT 0,
    internships INTEGER NOT NULL DEFAULT 0,
    new         INTEGER NOT NULL DEFAULT 0,
    closed      INTEGER NOT NULL DEFAULT 0,
    requests    INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    error       TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def start_run(conn: sqlite3.Connection, transport: str) -> int:
    cur = conn.execute("INSERT INTO runs (started_at, transport) VALUES (?, ?)", (now(), transport))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, **totals: int) -> None:
    sets = ", ".join(f"{k} = ?" for k in totals)
    conn.execute(f"UPDATE runs SET finished_at = ?{', ' + sets if sets else ''} WHERE id = ?",
                 (now(), *totals.values(), run_id))
    conn.commit()


def save_company(conn: sqlite3.Connection, run_id: int, company_id: str,
                 postings: list[Posting]) -> tuple[int, int]:
    """Upsert one company's postings for this run and close the ones that disappeared.
    Call only when the company was fetched completely. Returns (new, closed)."""
    ts = now()
    new = 0
    for p in postings:
        exists = conn.execute("SELECT 1 FROM postings WHERE key = ?", (p.key,)).fetchone()
        if exists:
            conn.execute(
                """UPDATE postings SET title = ?, location = ?, url = ?, posted_at = ?, posted_text = ?,
                   is_tech = ?, last_seen_run = ?, last_seen_at = ?, active = 1, closed_run = NULL
                   WHERE key = ?""",
                (p.title, p.location, p.url, p.posted_at, p.posted_text, int(p.is_tech), run_id, ts, p.key))
        else:
            new += 1
            conn.execute(
                """INSERT INTO postings (key, company_id, company, source, source_id, title, location, url,
                   posted_at, posted_text, is_tech, first_seen_run, last_seen_run, first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p.key, p.company_id, p.company, p.source, p.source_id, p.title, p.location, p.url,
                 p.posted_at, p.posted_text, int(p.is_tech), run_id, run_id, ts, ts))
    closed = conn.execute(
        """UPDATE postings SET active = 0, closed_run = ?
           WHERE company_id = ? AND active = 1 AND last_seen_run < ?""",
        (run_id, company_id, run_id)).rowcount
    conn.commit()
    return new, closed


def log_fetch(conn: sqlite3.Connection, run_id: int, company_id: str, *, ok: bool, jobs_seen: int = 0,
              internships: int = 0, new: int = 0, closed: int = 0, requests: int = 0,
              duration_ms: int = 0, error: str | None = None) -> None:
    conn.execute(
        """INSERT INTO fetch_log (run_id, company_id, ok, jobs_seen, internships, new, closed,
           requests, duration_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, company_id, int(ok), jobs_seen, internships, new, closed, requests, duration_ms, error))
    conn.commit()


def latest_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()


def query_postings(conn: sqlite3.Connection, *, company: list[str] | None = None, search: str | None = None,
                   location: str | None = None, tech: bool = False, since: str | None = None,
                   first_seen_run: int | None = None, closed_run: int | None = None,
                   include_closed: bool = False, sort: str = "posted", limit: int | None = None) -> list[dict]:
    where, args = [], []
    if closed_run is not None:
        where.append("closed_run = ?")
        args.append(closed_run)
    elif not include_closed:
        where.append("active = 1")
    if company:
        where.append(f"(company_id IN ({','.join('?' * len(company))}) OR lower(company) IN ({','.join('?' * len(company))}))")
        args += [c.lower() for c in company] * 2
    if search:
        where.append("lower(title) LIKE ?")
        args.append(f"%{search.lower()}%")
    if location:
        where.append("lower(location) LIKE ?")
        args.append(f"%{location.lower()}%")
    if tech:
        where.append("is_tech = 1")
    if since:
        where.append("posted_at >= ?")
        args.append(since)
    if first_seen_run is not None:
        where.append("first_seen_run = ?")
        args.append(first_seen_run)
    order = {
        "posted": "posted_at IS NULL, posted_at DESC, company, title",
        "company": "company, posted_at IS NULL, posted_at DESC, title",
        "title": "title, company",
    }[sort]
    sql = f"SELECT * FROM postings {'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in conn.execute(sql, args)]
