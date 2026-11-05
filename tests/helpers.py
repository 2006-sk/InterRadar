"""Shared test helpers: fixture loading and a fake fetch client (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from internradar.http import FetchError, FetchResult

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def fixture(name: str):
    path = FIXTURES / name
    return path.read_text() if path.suffix == ".md" else json.loads(path.read_text())


class FakeClient:
    """Answers fetch() from a dict of url -> data (or -> Exception / FetchResult)."""

    name = "fake"

    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []
        self.requests_made = 0

    def fetch(self, url: str, **options) -> FetchResult:
        self.calls.append((url, options))
        self.requests_made += 1
        if url not in self.responses:
            raise FetchError(f"FakeClient has no response for {url}")
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, FetchResult):
            return value
        return FetchResult(url=url, status_code=200, data=value, final_url=url)
