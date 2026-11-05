"""Recording responses and replaying them offline."""

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from internradar.http import FetchError
from internradar.snapshot import RecordingClient, ReplayClient, snapshot_name, trim

from .helpers import FakeClient, fixture


class TrimTest(unittest.TestCase):
    def test_drops_long_text_but_keeps_what_parsers_read(self):
        data = {"jobs": [{"id": 1, "title": "Intern", "descriptionHtml": "<p>long</p>", "content": "<p>long</p>",
                          "location": {"name": "NYC"}}]}
        self.assertEqual(trim(data), {"jobs": [{"id": 1, "title": "Intern", "location": {"name": "NYC"}}]})

    def test_keeps_smartrecruiters_content_list(self):
        page = fixture("smartrecruiters_page1.json")
        self.assertEqual(len(trim(page)["content"]), len(page["content"]))


class RecordReplayTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = FakeClient({"https://a.test/jobs": {"jobs": [{"id": 1, "title": "X Intern", "description": "long"}]},
                               "https://a.test/page": "# markdown"})
            rec = RecordingClient(live, tmp)
            rec.fetch("https://a.test/jobs")
            rec.fetch("https://a.test/page", format="markdown")
            self.assertEqual(rec.requests_made, 2)
            files = sorted(p.name for p in Path(tmp).iterdir())
            self.assertEqual(len(files), 2)
            self.assertTrue(all(f.endswith(".json.gz") for f in files))

            replay = ReplayClient(tmp)
            r = replay.fetch("https://a.test/jobs")
            self.assertEqual(r.data, {"jobs": [{"id": 1, "title": "X Intern"}]})  # trimmed
            self.assertEqual(replay.fetch("https://a.test/page", format="markdown").data, "# markdown")
            # Same URL with different options is a different snapshot entry.
            with self.assertRaises(FetchError):
                replay.fetch("https://a.test/page")

    def test_gzip_has_no_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            RecordingClient(FakeClient({"https://a.test/x": {"a": 1}}), tmp).fetch("https://a.test/x")
            raw = next(Path(tmp).iterdir()).read_bytes()
            self.assertEqual(raw[4:8], b"\x00\x00\x00\x00")  # gzip header MTIME field
            self.assertEqual(json.loads(gzip.decompress(raw))["data"], {"a": 1})

    def test_name_is_stable(self):
        self.assertEqual(snapshot_name("https://www.x.test/a", {"format": "markdown"}),
                         snapshot_name("https://www.x.test/a", {"format": "markdown"}))
        self.assertTrue(snapshot_name("https://www.x.test/a", {}).startswith("x.test-"))

    def test_missing_directory_is_fatal(self):
        with self.assertRaises(FetchError) as ctx:
            ReplayClient("/nonexistent/snapshot")
        self.assertTrue(ctx.exception.fatal)


if __name__ == "__main__":
    unittest.main()
