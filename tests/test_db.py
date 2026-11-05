"""SQLite storage: de-duplication, new/closed tracking, and queries."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from internradar import db
from internradar.models import DATA, SOFTWARE, Posting


def posting(source_id, title="Software Engineer Intern", company_id="acme", location="Remote", posted="2026-11-01"):
    return Posting(company_id, company_id.title(), "greenhouse", source_id, title, location,
                   f"https://jobs.test/{company_id}/{source_id}", posted)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")

    def run_with(self, company_id, postings):
        run = db.start_run(self.conn, "test")
        new, closed = db.save_company(self.conn, run, company_id, postings)
        db.finish_run(self.conn, run, postings_new=new, postings_closed=closed)
        return run, new, closed

    def active_keys(self):
        return {r["key"] for r in self.conn.execute("SELECT key FROM postings WHERE active = 1")}

    def test_new_closed_and_reopened(self):
        run1, new, closed = self.run_with("acme", [posting("1"), posting("2")])
        self.assertEqual((new, closed), (2, 0))

        # Seen again: not new. Posting 1 gone: closed. Posting 3 appears: new.
        run2, new, closed = self.run_with("acme", [posting("2"), posting("3")])
        self.assertEqual((new, closed), (1, 1))
        self.assertEqual(self.active_keys(), {"acme:2", "acme:3"})
        row = self.conn.execute("SELECT * FROM postings WHERE key = 'acme:1'").fetchone()
        self.assertEqual((row["active"], row["closed_run"]), (0, run2))
        self.assertEqual([r["key"] for r in db.query_postings(self.conn, first_seen_run=run2)], ["acme:3"])
        self.assertEqual([r["key"] for r in db.query_postings(self.conn, closed_run=run2)], ["acme:1"])

        # Posting 1 comes back: reactivated, but it isn't "new".
        run3, new, closed = self.run_with("acme", [posting("1"), posting("2"), posting("3")])
        self.assertEqual((new, closed), (0, 0))
        row = self.conn.execute("SELECT * FROM postings WHERE key = 'acme:1'").fetchone()
        self.assertEqual((row["active"], row["closed_run"], row["first_seen_run"]), (1, None, run1))

    def test_updates_changed_fields_but_keeps_first_seen(self):
        run1, _, _ = self.run_with("acme", [posting("1", title="Data Intern")])
        self.run_with("acme", [posting("1", title="Data Science Intern")])
        row = self.conn.execute("SELECT * FROM postings").fetchone()
        self.assertEqual((row["title"], row["first_seen_run"]), ("Data Science Intern", run1))

    def test_closing_is_per_company(self):
        self.run_with("acme", [posting("1")])
        self.run_with("globex", [posting("9", company_id="globex")])
        self.assertEqual(self.active_keys(), {"acme:1", "globex:9"})

    def test_query_filters(self):
        self.run_with("acme", [
            posting("1", "Software Engineer Intern", location="New York, NY", posted="2026-11-01"),
            posting("2", "Data Science Intern", location="London", posted="2026-10-01"),
            posting("3", "Marketing Intern", location="New York, NY", posted=None),
        ])
        q = lambda **kw: [r["source_id"] for r in db.query_postings(self.conn, **kw)]
        self.assertEqual(q(), ["1", "2", "3"])  # newest first, undated last
        self.assertEqual(q(search="software"), ["1"])
        self.assertEqual(q(location="new york"), ["1", "3"])
        self.assertEqual(q(since="2026-10-15"), ["1"])
        self.assertEqual(q(tech=True), ["1", "2"])
        self.assertEqual(q(category=["data"]), ["2"])
        self.assertEqual(q(company=["Acme"]), ["1", "2", "3"])
        self.assertEqual(q(company=["nobody"]), [])
        self.assertEqual(q(sort="title"), ["2", "3", "1"])
        self.assertEqual(q(limit=1), ["1"])
        rows = db.query_postings(self.conn)
        self.assertEqual([r["category"] for r in rows][:2], [SOFTWARE, DATA])

    def test_resolve_category(self):
        self.assertEqual(db.resolve_category("software"), SOFTWARE)
        self.assertEqual(db.resolve_category("Data & Research"), DATA)
        with self.assertRaises(ValueError):
            db.resolve_category("bogus")

    def test_latest_run_ignores_unfinished(self):
        self.run_with("acme", [posting("1")])
        db.start_run(self.conn, "test")  # crashed run, never finished
        self.assertEqual(db.latest_run(self.conn)["id"], 1)

    def test_old_schema_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            old = sqlite3.connect(path)
            old.executescript(db.SCHEMA.replace("    posted_text    TEXT NOT NULL DEFAULT '',",
                                                "    posted_text    TEXT NOT NULL DEFAULT '',\n    is_tech INTEGER NOT NULL DEFAULT 0,"))
            old.close()
            conn = db.connect(path)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(postings)")}
            conn.close()
            self.assertNotIn("is_tech", cols)


if __name__ == "__main__":
    unittest.main()
