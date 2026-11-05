"""End to end through the CLI, offline: replay the committed snapshot of a real
String run, then query it every way a user would. No network, no key."""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from internradar import cli

from .helpers import ROOT


def run_cli(*args) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class EndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(Path(cls.tmp.name) / "e2e.db")
        cls.code, cls.scrape_out, _ = run_cli("--db", cls.db, "scrape", "--transport", "replay", "--quiet")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cli(self, *args):
        return run_cli("--db", self.db, *args)

    def test_1_replay_scrape_covers_all_companies(self):
        self.assertEqual(self.code, 0, self.scrape_out)
        m = re.search(r"Run #1: (\d+)/(\d+) companies ok, (\d+) internships, (\d+) new", self.scrape_out)
        self.assertIsNotNone(m, self.scrape_out)
        ok, total, internships, new = map(int, m.groups())
        self.assertEqual((ok, total), (20, 20))
        self.assertGreater(internships, 500)
        self.assertEqual(new, internships)

    def test_2_json_output_is_normalised(self):
        code, out, _ = self.cli("list", "--format", "json")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertEqual(len({r["company"] for r in rows}), 20)
        for r in rows:
            self.assertTrue(r["company"] and r["title"])
            self.assertTrue(r["url"].startswith("https://"), r)
            self.assertTrue(r["posted_at"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["posted_at"]), r)
        self.assertIn("Stripe", {r["company"] for r in rows})

    def test_3_filters(self):
        _, out, _ = self.cli("list", "--format", "json", "--company", "stripe")
        self.assertTrue(json.loads(out))
        self.assertEqual({r["company"] for r in json.loads(out)}, {"Stripe"})
        _, out, _ = self.cli("list", "--format", "json", "--category", "software", "--location", "new york")
        rows = json.loads(out)
        self.assertTrue(rows)
        self.assertTrue(all(r["category"] == "Software" and "new york" in r["location"].lower() for r in rows))
        _, out, _ = self.cli("list", "--format", "json", "--since", "2026-11-01")
        self.assertTrue(all(r["posted_at"] >= "2026-11-01" for r in json.loads(out)))

    def test_4_table_and_html(self):
        code, out, _ = self.cli("list", "--search", "software", "--limit", "5")
        self.assertEqual(code, 0)
        self.assertIn("APPLY", out)
        self.assertIn("5 postings", out)
        page = Path(self.tmp.name) / "index.html"
        code, out, _ = self.cli("list", "--format", "html", "--out", str(page))
        self.assertEqual(code, 0)
        html = page.read_text()
        self.assertIn('<script id="data" type="application/json">', html)
        n = int(re.search(r"wrote (\d+) postings", out).group(1))
        self.assertGreater(n, 500)

    def test_5_second_run_reports_nothing_new(self):
        code, out, _ = self.cli("scrape", "--transport", "replay", "--quiet")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"Run #2: 20/20 companies ok, \d+ internships, 0 new, 0 closed")
        code, out, _ = self.cli("new")
        self.assertIn("0 postings new in run #2", out)
        code, out, _ = self.cli("runs")
        self.assertEqual(len([l for l in out.splitlines() if re.match(r"\s+\d+\s", l)]), 2)

    def test_6_companies_command(self):
        code, out, _ = self.cli("companies")
        self.assertEqual(code, 0)
        self.assertEqual(out.count(" ok, "), 20)

    def test_7_live_mode_without_a_key_fails_cleanly(self):
        with mock.patch.dict(os.environ, {"STRING_API_KEY": ""}):
            code, _, err = self.cli("scrape", "--company", "stripe")
        self.assertEqual(code, 2)
        self.assertIn("STRING_API_KEY is not set", err)

    def test_8_bad_input(self):
        code, _, err = self.cli("list", "--category", "bogus")
        self.assertEqual(code, 2)
        self.assertIn("unknown category", err)
        code, _, err = self.cli("scrape", "--transport", "replay", "--company", "nope")
        self.assertEqual(code, 2)

    def test_9_list_on_empty_db(self):
        code, _, err = run_cli("--db", str(Path(self.tmp.name) / "empty.db"), "list")
        self.assertEqual(code, 1)
        self.assertIn("No data yet", err)


if __name__ == "__main__":
    unittest.main()
