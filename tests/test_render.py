"""Table, JSON, CSV and HTML output."""

import csv
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from internradar import render


def row(**kw):
    base = {"company": "Acme", "company_id": "acme", "title": "Software Engineer Intern", "location": "New York, NY",
            "posted_at": "2026-11-01", "posted_text": "", "url": "https://jobs.test/acme/1", "source": "greenhouse",
            "first_seen_at": "2026-11-05T19:00:00+00:00", "first_seen_run": 1, "active": 1}
    return base | kw


class TableTest(unittest.TestCase):
    def test_full_url_and_new_marker(self):
        long_url = "https://jobs.test/" + "x" * 150
        out = render.table([row(url=long_url, first_seen_run=2), row(title="Data Intern")], new_run=2)
        lines = out.splitlines()
        self.assertIn("APPLY", lines[0])
        self.assertTrue(lines[2].startswith("* Acme"))
        self.assertTrue(lines[3].startswith("  Acme"))
        self.assertIn(long_url, out)  # never truncated

    def test_long_titles_are_truncated(self):
        out = render.table([row(title="T" * 100)])
        self.assertIn("…", out)

    def test_undated_and_vague_dates(self):
        out = render.table([row(posted_at=None, posted_text="30+ days ago"), row(posted_at=None)], show_url=False)
        self.assertIn("30+ days ago", out)
        self.assertIn("—", out)

    def test_empty(self):
        self.assertEqual(render.table([]), "(no postings match)")


class JsonCsvTest(unittest.TestCase):
    def test_json_has_the_normalised_fields(self):
        data = json.loads(render.to_json([row()], new_run=1))
        for key in ("company", "title", "location", "posted_at", "url", "category", "new"):
            self.assertIn(key, data[0])
        self.assertEqual(data[0]["category"], "Software")
        self.assertTrue(data[0]["new"])

    def test_csv(self):
        rows = list(csv.DictReader(io.StringIO(render.to_csv([row(), row(title="Data Intern")]))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["title"], "Data Intern")


class HtmlTest(unittest.TestCase):
    def embedded(self, page):
        blob = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
        return json.loads(blob)

    def test_embeds_rows_and_meta(self):
        page = render.to_html([row(), row(company="Globex", title="Hardware Engineer Intern")], new_run=None,
                              generated_at="2026-11-05T19:51:05+00:00")
        data = self.embedded(page)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["meta"]["companies"], [["Acme", 1], ["Globex", 1]])
        self.assertFalse(data["meta"]["hasPreviousRun"])
        self.assertEqual(dict(data["meta"]["categories"])["Hardware & Engineering"], 1)

    def test_script_injection_in_a_title_cannot_break_out(self):
        page = render.to_html([row(title="Intern</script><script>alert(1)</script>")])
        self.assertEqual(page.count("</script>"), 2)  # only the page's own two script blocks
        self.assertEqual(self.embedded(page)["rows"][0]["t"], "Intern</script><script>alert(1)</script>")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_inline_javascript_parses(self):
        page = render.to_html([row()])
        script = page.rsplit("<script>", 1)[1].split("</script>")[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(script)
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
