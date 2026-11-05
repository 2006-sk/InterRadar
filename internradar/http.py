"""HTTP transports.

`StringClient` sends every request through String Web Access (POST /v1/fetch).
`DirectClient` does a plain GET, for people without a String key. Both return a
`FetchResult` and space out requests politely.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

USER_AGENT = "internradar/0.1 (+https://github.com/2006-sk/Stringinterview)"


class FetchError(Exception):
    """A fetch failed. `fatal` means stop the whole run (bad key, no balance)."""

    def __init__(self, message: str, *, status: int | None = None, fatal: bool = False):
        super().__init__(message)
        self.status = status
        self.fatal = fatal


@dataclass
class FetchResult:
    url: str
    status_code: int  # status the *destination* returned
    data: Any  # parsed JSON (dict/list) or text
    final_url: str = ""
    billed_type: str = ""  # String's x-billed-request-type header
    request_id: str = ""
    duration_ms: int = 0
    meta: dict = field(default_factory=dict)


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class _Pacer:
    """Enforces a minimum gap between requests (polite pace)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


class StringClient:
    """Read-only client for String Web Access `POST /v1/fetch`."""

    name = "string"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://request.usestring.ai/v1",
        min_interval: float = 1.5,
        timeout: float = 120,
        max_retries: int = 3,
    ):
        if not api_key:
            raise FetchError("STRING_API_KEY is not set (see .env.example)", fatal=True)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.pacer = _Pacer(min_interval)
        self.requests_made = 0

    def fetch(self, url: str, **options: Any) -> FetchResult:
        """GET `url` through String. `options` are passed to /fetch as-is
        (e.g. format="markdown", executeJS=True, jsonSchema={...})."""
        if options.get("method", "GET").upper() != "GET":
            raise ValueError("internradar is read-only: only GET requests are allowed")
        body = json.dumps({"url": url, **options}).encode()
        attempt = 0
        while True:
            attempt += 1
            self.pacer.wait()
            req = urllib.request.Request(
                f"{self.base_url}/fetch",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            t0 = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self.requests_made += 1
                    raw = resp.read().decode("utf-8", errors="replace")
                    headers = resp.headers
                    common = dict(
                        url=url,
                        billed_type=headers.get("x-billed-request-type", ""),
                        request_id=headers.get("x-request-id", ""),
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                    if options.get("format", "json") != "json":
                        # markdown/raw: body is the page itself; status lives in headers.
                        return FetchResult(
                            status_code=int(headers.get("x-status-code") or 0),
                            data=raw,
                            final_url=headers.get("x-final-url") or url,
                            **common,
                        )
                    payload = json.loads(raw)
                    if headers.get("x-json-schema-applied", "").lower() == "true":
                        # jsonSchema extraction: the body *is* the extracted object.
                        return FetchResult(
                            status_code=int(headers.get("x-status-code") or 0),
                            data=payload,
                            final_url=headers.get("x-final-url") or url,
                            **common,
                        )
                    return FetchResult(
                        status_code=int(payload.get("statusCode") or 0),
                        data=payload.get("data"),
                        final_url=payload.get("finalUrl") or url,
                        meta={k: v for k, v in payload.items() if k not in ("data", "headers")},
                        **common,
                    )
            except urllib.error.HTTPError as e:
                self.requests_made += 1
                detail = _error_detail(e)
                if e.code in (401, 402):
                    raise FetchError(f"String {e.code}: {detail}", status=e.code, fatal=True)
                retryable = e.code in (429, 500, 502, 503, 504)
                if retryable and attempt <= self.max_retries:
                    delay = float(e.headers.get("Retry-After") or 0) or 2 ** attempt
                    time.sleep(min(delay, 30))
                    continue
                raise FetchError(f"String {e.code}: {detail}", status=e.code)
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt <= self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise FetchError(f"network error talking to String: {e}")


class DirectClient:
    """Plain GET without String, for anyone who has no String key.
    Same interface as StringClient; JS rendering / extraction options are ignored."""

    name = "direct"

    def __init__(self, min_interval: float = 1.5, timeout: float = 60):
        self.pacer = _Pacer(min_interval)
        self.timeout = timeout
        self.requests_made = 0

    def fetch(self, url: str, **options: Any) -> FetchResult:
        if options.get("executeJS") or options.get("jsonSchema") or options.get("actions"):
            raise FetchError("this source needs String (JS rendering / extraction); skipped in direct mode")
        self.pacer.wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.requests_made += 1
                raw = resp.read().decode("utf-8", errors="replace")
                status = resp.status
                final = resp.geturl()
        except urllib.error.HTTPError as e:
            self.requests_made += 1
            raw, status, final = e.read().decode("utf-8", errors="replace"), e.code, url
        except (urllib.error.URLError, TimeoutError) as e:
            raise FetchError(f"network error: {e}")
        try:
            data: Any = json.loads(raw)
        except ValueError:
            data = raw
        return FetchResult(url=url, status_code=status, data=data, final_url=final,
                           duration_ms=int((time.monotonic() - t0) * 1000))


def _error_detail(e: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(e.read().decode("utf-8"))
        return body.get("message") or body.get("reason") or body.get("error") or str(body)
    except Exception:
        return e.reason or "unknown error"
