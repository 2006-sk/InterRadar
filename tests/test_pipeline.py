"""The connected pipeline: config -> sources -> normalise -> SQLite, across runs."""

import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from internradar import db
from internradar.http import FetchError
from internradar.pipeline import dedupe, load_companies, scrape
from internradar.sources import greenhouse, janestreet, workday

from .helpers import ROOT, FakeClient, fixture

TODAY = date(2026, 11, 5)
COMPANIES = [
    {"id": "stripe", "name": "Stripe", "source": "greenhouse", "board": "stripe"},
    {"id": "janestreet", "name": "Jane Street", "source": "janestreet"},
    {"id": "nvidia", "name": "NVIDIA", "source": "workday", "host": "nvidia.wd5.myworkdayjobs.com",
     "site": "NVIDIAExternalCareerSite", "query": "intern"},
]
GH_URL, JS_URL, WD_URL = greenhouse.url(COMPANIES[0]), janestreet.url(COMPANIES[1]), workday.url(COMPANIES[2])


def responses(**overrides):
    base = {GH_URL: fixture("greenhouse.json"), JS_URL: fixture("janestreet.json"), WD_URL: fixture("workday.md")}
    base.update(overrides)
    return base


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.log = []

    def run_once(self, resp):
        return scrape(self.conn, COMPANIES, FakeClient(resp), TODAY, log=self.log.append)

    def test_first_run_stores_everything(self):
        s = self.run_once(responses())
        self.assertEqual((s.ok, s.failed), (3, 0))
        self.assertEqual([r.internships for r in s.results], [3, 2, 3])
        self.assertEqual(s.new, 8)
        run = db.latest_run(self.conn)
        self.assertEqual((run["companies_ok"], run["postings_new"], run["requests"]), (3, 8, 3))
        self.assertEqual(len(self.log), 3)

    def test_second_run_finds_new_and_closed(self):
        self.run_once(responses())
        changed = copy.deepcopy(fixture("greenhouse.json"))
        changed["jobs"] = [j for j in changed["jobs"] if j["id"] != 8194287]  # one internship removed
        changed["jobs"].append({"id": 999, "title": "Software Engineer Intern", "location": {"name": "Dublin"},
                                "absolute_url": "https://stripe.com/jobs/search?gh_jid=999",
                                "first_published": "2026-11-05T09:00:00-04:00"})
        s = self.run_once(responses(**{GH_URL: changed}))
        stripe = s.results[0]
        self.assertEqual((stripe.new, stripe.closed), (1, 1))
        self.assertEqual(s.new, 1)
        new_rows = db.query_postings(self.conn, first_seen_run=s.run_id)
        self.assertEqual([r["key"] for r in new_rows], ["stripe:999"])

    def test_unchanged_rerun_has_nothing_new(self):
        self.run_once(responses())
        s = self.run_once(responses())
        self.assertEqual((s.new, sum(r.closed for r in s.results)), (0, 0))

    def test_failed_company_keeps_its_postings_open(self):
        self.run_once(responses())
        s = self.run_once(responses(**{JS_URL: FetchError("String 502: destination error", status=502)}))
        js = s.results[1]
        self.assertFalse(js.ok)
        self.assertIn("502", js.error)
        self.assertEqual(js.closed, 0)
        still_open = db.query_postings(self.conn, company=["janestreet"])
        self.assertEqual(len(still_open), 2)  # a failed fetch must not look like "all postings closed"
        self.assertEqual(s.ok, 2)

    def test_fatal_error_stops_the_run(self):
        s = self.run_once(responses(**{GH_URL: FetchError("String 402: Insufficient balance", status=402, fatal=True)}))
        self.assertEqual(s.ok, 0)
        self.assertIn("402", s.aborted)
        self.assertTrue(all(r.error.startswith("skipped") for r in s.results[1:]))
        self.assertIsNotNone(db.latest_run(self.conn)["finished_at"])

    def test_parser_bug_in_one_source_does_not_sink_the_run(self):
        broken = {"jobs": [{"title": "Data Intern"}]}  # no "id"
        s = self.run_once(responses(**{GH_URL: broken}))
        self.assertFalse(s.results[0].ok)
        self.assertIn("KeyError", s.results[0].error)
        self.assertEqual(s.ok, 2)

    def test_dedupe_within_one_fetch(self):
        postings, _ = greenhouse.parse(fixture("greenhouse.json"), COMPANIES[0], TODAY)
        self.assertEqual(len(dedupe(postings + postings)), len(postings))


class CompaniesConfigTest(unittest.TestCase):
    def test_shipped_config(self):
        companies = load_companies(ROOT / "companies.json")
        self.assertEqual(len(companies), 20)
        self.assertEqual(len({c["id"] for c in companies}), 20)
        self.assertIn("stripe", {c["id"] for c in companies})

    def test_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            path.write_text(json.dumps([{"id": "x", "name": "X", "source": "monster"}]))
            with self.assertRaisesRegex(ValueError, "unknown source"):
                load_companies(path)
            path.write_text(json.dumps([{"id": "x", "source": "lever"}]))
            with self.assertRaisesRegex(ValueError, "missing"):
                load_companies(path)


if __name__ == "__main__":
    unittest.main()
