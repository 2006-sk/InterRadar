"""Each source parser against a fixture cut from a real response."""

import unittest
from datetime import date

from internradar.http import FetchError, FetchResult
from internradar.sources import SOURCES, amazon, ashby, greenhouse, janestreet, lever, smartrecruiters, workday
from internradar.sources.base import expect_ok

from .helpers import FakeClient, fixture

TODAY = date(2026, 11, 5)


def cfg(company_id, name, **extra):
    return {"id": company_id, "name": name, **extra}


class GreenhouseTest(unittest.TestCase):
    def test_parse(self):
        postings, seen = greenhouse.parse(fixture("greenhouse.json"), cfg("stripe", "Stripe", board="stripe"), TODAY)
        self.assertEqual(seen, 6)
        self.assertEqual([p.title for p in postings],
                         ["Data Analyst, Intern", "Data Analyst, Intern", "Financial Data Analyst Intern, Technical Operations"])
        first = postings[0]
        self.assertEqual(first.key, "stripe:8194291")
        self.assertEqual(first.location, "New York, Seattle, South San Francisco HQ")
        self.assertEqual(first.url, "https://stripe.com/jobs/search?gh_jid=8194291")
        self.assertEqual(first.posted_at, "2026-10-01")  # first_published, not updated_at

    def test_url(self):
        self.assertEqual(greenhouse.url({"board": "stripe"}), "https://boards-api.greenhouse.io/v1/boards/stripe/jobs")


class LeverTest(unittest.TestCase):
    def test_parse_uses_commitment_flag(self):
        postings, seen = lever.parse(fixture("lever.json"), cfg("palantir", "Palantir", board="palantir"), TODAY)
        self.assertEqual(seen, 5)
        titles = [p.title for p in postings]
        self.assertIn("Meritocracy Fellowship", titles)  # commitment says "Internship"
        self.assertNotIn("American Tech Fellowship", titles)  # commitment says "Scholarship"
        self.assertEqual(len(postings), 3)
        self.assertEqual(postings[0].posted_at, "2026-05-11")
        self.assertEqual(postings[0].location, "Paris, France")
        self.assertTrue(postings[0].url.startswith("https://jobs.lever.co/palantir/"))


class AshbyTest(unittest.TestCase):
    def test_parse(self):
        postings, seen = ashby.parse(fixture("ashby.json"), cfg("notion", "Notion", board="notion"), TODAY)
        self.assertEqual(seen, 4)
        self.assertEqual([p.title for p in postings], ["Software Engineer Intern (Summer 2027)", "Cohort 0"])
        self.assertEqual(postings[0].location, "San Francisco, California; New York, New York")
        self.assertEqual(postings[0].posted_at, "2026-08-14")

    def test_unlisted_jobs_are_skipped(self):
        postings, _ = ashby.parse(fixture("ashby.json"), cfg("notion", "Notion"), TODAY)
        self.assertNotIn("hidden-intern-1", [p.source_id for p in postings])

    def test_remote_is_added_to_location(self):
        data = {"jobs": [{"id": "1", "title": "Data Intern", "location": "United States", "workplaceType": "Remote",
                          "isListed": True, "jobUrl": "https://x", "publishedAt": None}]}
        postings, _ = ashby.parse(data, cfg("x", "X"), TODAY)
        self.assertEqual(postings[0].location, "United States; Remote")


class SmartRecruitersTest(unittest.TestCase):
    def test_paginates_until_total_found(self):
        c = cfg("servicenow", "ServiceNow", board="ServiceNow", query="intern", max_pages=5)
        client = FakeClient({smartrecruiters.url(c, 0): fixture("smartrecruiters_page1.json"),
                             smartrecruiters.url(c, 100): fixture("smartrecruiters_page2.json")})
        postings, seen = smartrecruiters.fetch(c, client, TODAY)
        self.assertEqual(len(client.calls), 2)  # totalFound=150 -> offsets 0 and 100, then stop
        self.assertEqual(seen, 5)
        self.assertEqual(len(postings), 3)
        self.assertEqual(postings[0].url, "https://jobs.smartrecruiters.com/ServiceNow/744000159255618")
        self.assertEqual(postings[0].posted_at, "2026-11-02")

    def test_max_pages_caps_requests(self):
        c = cfg("servicenow", "ServiceNow", board="ServiceNow", max_pages=1)
        client = FakeClient({smartrecruiters.url(c, 0): fixture("smartrecruiters_page1.json")})
        smartrecruiters.fetch(c, client, TODAY)
        self.assertEqual(len(client.calls), 1)

    def test_a_failed_page_fails_the_company(self):
        c = cfg("servicenow", "ServiceNow", board="ServiceNow")
        client = FakeClient({smartrecruiters.url(c, 0): fixture("smartrecruiters_page1.json")})  # page 2 missing
        with self.assertRaises(FetchError):
            smartrecruiters.fetch(c, client, TODAY)


class AmazonTest(unittest.TestCase):
    def test_parse(self):
        postings, seen = amazon.parse(fixture("amazon.json"), cfg("amazon", "Amazon"), TODAY)
        self.assertEqual(seen, 4)
        self.assertEqual(len(postings), 4)  # includes the German "Praktikum"
        self.assertEqual(postings[0].posted_at, "2026-11-05")  # "November  5, 2026" (double space)
        self.assertEqual(postings[0].url, "https://www.amazon.jobs/en/jobs/10597338/assembly-operator-intern-rivr")

    def test_same_title_and_city_with_different_req_ids_are_different_postings(self):
        postings, _ = amazon.parse(fixture("amazon.json"), cfg("amazon", "Amazon"), TODAY)
        rivr = [p for p in postings if p.title == "Assembly Operator Intern, RIVR"]
        self.assertEqual(len({p.key for p in rivr}), 2)

    def test_pagination_stops_at_hits(self):
        c = cfg("amazon", "Amazon", max_pages=5)
        page = fixture("amazon.json") | {"hits": 150}
        client = FakeClient({amazon.url(c, 0): page, amazon.url(c, 100): page})
        amazon.fetch(c, client, TODAY)
        self.assertEqual([u for u, _ in client.calls], [amazon.url(c, 0), amazon.url(c, 100)])


class JaneStreetTest(unittest.TestCase):
    def test_parse_uses_availability(self):
        postings, seen = janestreet.parse(fixture("janestreet.json"), cfg("janestreet", "Jane Street"), TODAY)
        self.assertEqual(seen, 3)
        self.assertEqual(len(postings), 2)
        p = postings[0]
        self.assertEqual(p.title, "Cybersecurity Engineer (Summer Internship)")
        self.assertEqual(p.location, "New York")
        self.assertIsNone(p.posted_at)
        self.assertEqual(p.url, "https://www.janestreet.com/join-jane-street/position/8632723002/")


class WorkdayTest(unittest.TestCase):
    CFG = cfg("nvidia", "NVIDIA", host="nvidia.wd5.myworkdayjobs.com", site="NVIDIAExternalCareerSite", query="intern")

    def test_parse_markdown(self):
        postings, seen = workday.parse(fixture("workday.md"), self.CFG, TODAY)
        self.assertEqual(seen, 4)
        self.assertEqual([p.source_id for p in postings], ["JR2027176", "JR2024692", "JR2026972"])  # not the tax director
        first = postings[0]
        self.assertEqual(first.title, "DFT Intern - 2027")
        self.assertEqual(first.location, "China, Shanghai")
        self.assertEqual(first.posted_at, "2026-10-13")  # "Posted 23 Days Ago"
        self.assertNotIn("?q=", first.url)
        vague = postings[1]
        self.assertIsNone(vague.posted_at)
        self.assertEqual(vague.posted_text, "30+ days ago")

    def test_fetch_asks_string_to_render(self):
        client = FakeClient({workday.url(self.CFG): fixture("workday.md")})
        workday.fetch(self.CFG, client, TODAY)
        options = client.calls[0][1]
        self.assertTrue(options["executeJS"])
        self.assertEqual(options["format"], "markdown")


class BaseTest(unittest.TestCase):
    def test_expect_ok_rejects_bad_status_and_shape(self):
        with self.assertRaises(FetchError):
            expect_ok(FetchResult(url="u", status_code=404, data={}))
        with self.assertRaises(FetchError):
            expect_ok(FetchResult(url="u", status_code=200, data="<html>"), dict)
        self.assertEqual(expect_ok(FetchResult(url="u", status_code=200, data={"a": 1}), dict), {"a": 1})

    def test_registry(self):
        self.assertEqual(set(SOURCES), {"greenhouse", "lever", "ashby", "smartrecruiters", "amazon", "janestreet", "workday"})


if __name__ == "__main__":
    unittest.main()
