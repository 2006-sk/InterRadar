"""Command-line interface: `python -m internradar <command>` (or `intern-radar <command>`)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import db, render
from .http import DirectClient, FetchError, StringClient, load_dotenv
from .pipeline import load_companies, scrape
from .snapshot import RecordingClient, ReplayClient

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(ROOT / ".env")
    args = build_parser().parse_args(argv)
    if not args.command:
        build_parser().print_help()
        return 1
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)
    try:
        return args.func(args, conn)
    except (FetchError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="intern-radar", description="Internship openings from many careers sites, in one list.")
    p.add_argument("--db", default=os.environ.get("INTERNRADAR_DB", str(ROOT / "data" / "internradar.db")),
                   help="SQLite file (default: data/internradar.db)")
    p.add_argument("--config", default=str(ROOT / "companies.json"), help="companies file (default: companies.json)")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("scrape", help="fetch every company and update the database")
    s.add_argument("--company", action="append", metavar="ID", help="only these company ids (repeatable)")
    s.add_argument("--transport", choices=["string", "direct", "replay"], default="string",
                   help="string = through String Web Access (default); replay = from the snapshot, no network; "
                        "direct = plain GET without String")
    s.add_argument("--snapshot", default=str(ROOT / "snapshot"), help="snapshot directory (default: snapshot/)")
    s.add_argument("--record", action="store_true", help="save responses to the snapshot directory")
    s.add_argument("--delay", type=float, default=1.5, help="seconds between requests (default 1.5)")
    s.add_argument("--quiet", action="store_true", help="only print the summary")
    s.set_defaults(func=cmd_scrape)

    for name, helptext in (("list", "show open internships"), ("new", "show postings first seen in the latest run")):
        lp = sub.add_parser(name, help=helptext)
        lp.add_argument("--company", action="append", metavar="ID", help="company id or name (repeatable)")
        lp.add_argument("--search", "-s", help="text in the role title, e.g. 'software'")
        lp.add_argument("--location", "-l", help="text in the location, e.g. 'new york' or 'remote'")
        lp.add_argument("--tech", action="store_true",
                        help="technical roles only (Software, Data & Research, Hardware & Engineering)")
        lp.add_argument("--category", "-c", action="append", metavar="NAME",
                        help="software | data | hardware | other (repeatable)")
        lp.add_argument("--since", metavar="YYYY-MM-DD", help="posted on or after this date")
        lp.add_argument("--sort", choices=["posted", "company", "title"], default="posted")
        lp.add_argument("--limit", type=int)
        lp.add_argument("--format", "-f", choices=["table", "json", "csv", "html"], default="table")
        lp.add_argument("--out", "-o", help="write to this file instead of stdout")
        lp.add_argument("--no-url", action="store_true", help="hide the link column in table output")
        if name == "list":
            lp.add_argument("--include-closed", action="store_true", help="also show postings that have closed")
            lp.set_defaults(func=cmd_list)
        else:
            lp.add_argument("--closed", action="store_true", help="show postings that closed in the latest run instead")
            lp.set_defaults(func=cmd_new)

    c = sub.add_parser("companies", help="show configured companies and how their last fetch went")
    c.set_defaults(func=cmd_companies)
    r = sub.add_parser("runs", help="show scrape history")
    r.set_defaults(func=cmd_runs)
    return p


def make_client(args):
    if args.transport == "replay":
        return ReplayClient(args.snapshot)
    if args.transport == "direct":
        client = DirectClient(min_interval=args.delay)
    else:
        key = os.environ.get("STRING_API_KEY", "")
        if not key or key == "paste-your-key-here":
            raise FetchError("STRING_API_KEY is not set. Copy .env.example to .env and add your key, "
                             "or run with --transport replay to use the saved snapshot.", fatal=True)
        client = StringClient(key, os.environ.get("STRING_BASE_URL", "https://request.usestring.ai/v1"),
                              min_interval=args.delay)
    return RecordingClient(client, args.snapshot) if args.record else client


def cmd_scrape(args, conn) -> int:
    companies = load_companies(args.config)
    if args.company:
        wanted = {c.lower() for c in args.company}
        companies = [c for c in companies if c["id"].lower() in wanted]
        if not companies:
            print(f"error: no company with id in {sorted(wanted)}; see `intern-radar companies`", file=sys.stderr)
            return 2
    client = make_client(args)
    print(f"Scraping {len(companies)} companies via {client.name}"
          f"{' (recording snapshot)' if args.record else ''}...")
    summary = scrape(conn, companies, client, log=(lambda _: None) if args.quiet else print)
    total = sum(r.internships for r in summary.results)
    print(f"\nRun #{summary.run_id}: {summary.ok}/{len(companies)} companies ok, {total} internships, "
          f"{summary.new} new, {sum(r.closed for r in summary.results)} closed, {client.requests_made} requests.")
    for r in summary.results:
        if not r.ok:
            print(f"  ! {r.name}: {r.error}")
    if summary.aborted:
        print(f"Run stopped early: {summary.aborted}", file=sys.stderr)
    first_run = conn.execute("SELECT count(*) FROM runs WHERE finished_at IS NOT NULL").fetchone()[0] == 1
    if summary.new and not first_run:
        print("\nNew since the last run:")
        print(render.table(db.query_postings(conn, first_seen_run=summary.run_id), new_run=summary.run_id))
    return 0 if summary.ok else 1


def _filters(args) -> dict:
    return dict(company=args.company, search=args.search, location=args.location, tech=args.tech,
                category=args.category, since=args.since, sort=args.sort, limit=args.limit)


def _output(args, conn, rows, new_run) -> None:
    if args.format == "table":
        text = render.table(rows, new_run=new_run, show_url=not args.no_url)
    elif args.format == "json":
        text = render.to_json(rows, new_run)
    elif args.format == "csv":
        text = render.to_csv(rows, new_run)
    else:
        latest = db.latest_run(conn)
        text = render.to_html(rows, new_run, generated_at=(latest["finished_at"] if latest else ""))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text if text.endswith("\n") else text + "\n")
        print(f"wrote {len(rows)} postings to {args.out}")
    else:
        print(text)


def _new_run_id(conn) -> int | None:
    """The latest run, unless it was the very first one (then 'new' means nothing)."""
    runs = conn.execute("SELECT id FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 2").fetchall()
    return runs[0]["id"] if len(runs) == 2 else None


def cmd_list(args, conn) -> int:
    if not db.latest_run(conn):
        print("No data yet. Run `intern-radar scrape` first (or `scrape --transport replay`).", file=sys.stderr)
        return 1
    rows = db.query_postings(conn, include_closed=args.include_closed, **_filters(args))
    _output(args, conn, rows, _new_run_id(conn))
    if args.format == "table" and not args.out:
        print(f"\n{len(rows)} postings. * = new since the previous run.")
    return 0


def cmd_new(args, conn) -> int:
    latest = db.latest_run(conn)
    if not latest:
        print("No data yet. Run `intern-radar scrape` first.", file=sys.stderr)
        return 1
    if args.closed:
        rows = db.query_postings(conn, closed_run=latest["id"], **_filters(args))
        label = "closed (gone from the site) in"
    else:
        if _new_run_id(conn) is None:
            print("Only one run so far, so everything is new. Run `scrape` again later to see what changed.")
            return 0
        rows = db.query_postings(conn, first_seen_run=latest["id"], **_filters(args))
        label = "new in"
    _output(args, conn, rows, latest["id"] if not args.closed else None)
    if args.format == "table" and not args.out:
        print(f"\n{len(rows)} postings {label} run #{latest['id']} ({latest['finished_at']}).")
    return 0


def cmd_companies(args, conn) -> int:
    companies = load_companies(args.config)
    last = {r["company_id"]: r for r in conn.execute(
        """SELECT f.* FROM fetch_log f JOIN (SELECT company_id, max(run_id) AS run_id FROM fetch_log GROUP BY company_id) m
           USING (company_id, run_id)""")}
    active = dict(conn.execute("SELECT company_id, count(*) FROM postings WHERE active = 1 GROUP BY company_id").fetchall())
    print(f"{'ID':<12} {'NAME':<14} {'SOURCE':<16} {'OPEN':>5}  LAST FETCH")
    for c in companies:
        f = last.get(c["id"])
        status = "never" if not f else (f"ok, {f['jobs_seen']} jobs scanned, run #{f['run_id']}" if f["ok"]
                                         else f"FAILED run #{f['run_id']}: {f['error']}")
        print(f"{c['id']:<12} {c['name']:<14} {c['source']:<16} {active.get(c['id'], 0):>5}  {status}")
    return 0


def cmd_runs(args, conn) -> int:
    print(f"{'RUN':>4}  {'FINISHED (UTC)':<26} {'VIA':<7} {'OK':>3} {'FAIL':>4} {'SEEN':>5} {'NEW':>5} {'CLOSED':>6} {'REQS':>5}")
    for r in conn.execute("SELECT * FROM runs ORDER BY id"):
        print(f"{r['id']:>4}  {(r['finished_at'] or 'unfinished'):<26} {r['transport'] or '':<7} {r['companies_ok']:>3} "
              f"{r['companies_failed']:>4} {r['postings_seen']:>5} {r['postings_new']:>5} {r['postings_closed']:>6} {r['requests']:>5}")
    return 0
