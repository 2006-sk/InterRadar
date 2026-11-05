"""StringClient against a local fake String server (real HTTP, no internet)."""

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from internradar.http import DirectClient, FetchError, StringClient


class FakeString(BaseHTTPRequestHandler):
    calls: list = []
    attempts: dict = {}

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status, body, headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeString.calls.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        url = body["url"]
        n = FakeString.attempts[url] = FakeString.attempts.get(url, 0) + 1
        if url == "https://site.test/json":
            self._send(200, {"statusCode": 200, "headers": {}, "data": {"jobs": [1, 2]}, "finalUrl": url},
                       {"x-billed-request-type": "request_standard", "x-request-id": "req-1"})
        elif url == "https://site.test/page" and body.get("format") == "markdown":
            self._send(200, b"# Jobs\n\n### [A](https://x)", {"x-status-code": "200", "x-final-url": url + "/final",
                                                                "x-billed-request-type": "browser_standard"})
        elif url == "https://site.test/schema":
            self._send(200, {"jobs": [{"title": "T"}]}, {"x-json-schema-applied": "true", "x-status-code": "200"})
        elif url == "https://site.test/404":
            self._send(200, {"statusCode": 404, "data": "not found", "finalUrl": url})
        elif url == "https://site.test/flaky":
            if n == 1:
                self._send(429, {"error": "Rate limit exceeded"}, {"Retry-After": "0"})
            else:
                self._send(200, {"statusCode": 200, "data": {"ok": True}, "finalUrl": url})
        elif url == "https://site.test/badkey":
            self._send(401, {"error": "Invalid API key"})
        elif url == "https://site.test/broke":
            self._send(402, {"error": "Insufficient balance"})
        elif url == "https://site.test/kyc":
            self._send(403, {"reason": "POST requests to this path are blocked pending KYC."})
        else:
            self._send(400, {"error": "Validation error", "message": "unexpected url"})


class StringClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeString)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeString.calls.clear()
        FakeString.attempts.clear()
        self.client = StringClient("test-key", self.base, min_interval=0, max_retries=2)

    def test_json_envelope(self):
        r = self.client.fetch("https://site.test/json")
        self.assertEqual((r.status_code, r.data, r.billed_type, r.request_id), (200, {"jobs": [1, 2]}, "request_standard", "req-1"))
        call = FakeString.calls[0]
        self.assertEqual(call["path"], "/v1/fetch")
        self.assertEqual(call["auth"], "Bearer test-key")
        self.assertEqual(call["body"], {"url": "https://site.test/json"})

    def test_markdown_body_is_not_json(self):
        # Regression: the first client assumed a JSON envelope for every format.
        r = self.client.fetch("https://site.test/page", format="markdown", executeJS=True)
        self.assertEqual(r.data, "# Jobs\n\n### [A](https://x)")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.final_url, "https://site.test/page/final")
        self.assertEqual(FakeString.calls[0]["body"]["executeJS"], True)

    def test_json_schema_body_is_the_extracted_object(self):
        r = self.client.fetch("https://site.test/schema", jsonSchema={"type": "object"})
        self.assertEqual(r.data, {"jobs": [{"title": "T"}]})

    def test_destination_status_is_reported_not_raised(self):
        self.assertEqual(self.client.fetch("https://site.test/404").status_code, 404)

    def test_retries_429_using_retry_after(self):
        t0 = time.monotonic()
        r = self.client.fetch("https://site.test/flaky")
        self.assertEqual(r.data, {"ok": True})
        self.assertEqual(FakeString.attempts["https://site.test/flaky"], 2)
        self.assertLess(time.monotonic() - t0, 1.5)  # Retry-After: 0 means no 2s backoff

    def test_bad_key_and_no_balance_are_fatal(self):
        for url in ("https://site.test/badkey", "https://site.test/broke"):
            with self.subTest(url=url), self.assertRaises(FetchError) as ctx:
                self.client.fetch(url)
            self.assertTrue(ctx.exception.fatal)

    def test_blocked_request_is_not_fatal_and_keeps_reason(self):
        with self.assertRaises(FetchError) as ctx:
            self.client.fetch("https://site.test/kyc")
        self.assertFalse(ctx.exception.fatal)
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("KYC", str(ctx.exception))

    def test_read_only_guard(self):
        with self.assertRaises(ValueError):
            self.client.fetch("https://site.test/json", method="POST", body={"x": 1})
        self.assertEqual(FakeString.calls, [])  # nothing was sent

    def test_polite_pacing(self):
        client = StringClient("test-key", self.base, min_interval=0.3)
        t0 = time.monotonic()
        client.fetch("https://site.test/json")
        client.fetch("https://site.test/json")
        self.assertGreaterEqual(time.monotonic() - t0, 0.3)
        self.assertEqual(client.requests_made, 2)

    def test_missing_key(self):
        with self.assertRaises(FetchError) as ctx:
            StringClient("")
        self.assertTrue(ctx.exception.fatal)


class DirectClientTest(unittest.TestCase):
    def test_refuses_options_that_need_string(self):
        client = DirectClient(min_interval=0)
        for opts in ({"executeJS": True}, {"jsonSchema": {}}, {"actions": [{"type": "wait"}]}):
            with self.subTest(opts=opts), self.assertRaises(FetchError):
                client.fetch("https://example.test", **opts)


if __name__ == "__main__":
    unittest.main()
