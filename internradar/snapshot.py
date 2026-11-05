"""Record String responses to disk (gzipped JSON) and replay them later without a key.

`RecordingClient` wraps a live client and writes each response (minus long
description fields) to a snapshot directory. `ReplayClient` serves those files
back, so the whole pipeline can run offline: for tests, demos, or after the key
has been revoked.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .http import FetchError, FetchResult

# Long text fields no parser reads. Dropping them keeps the snapshot small.
HEAVY_KEYS = {
    "content", "description", "descriptionHtml", "descriptionPlain", "descriptionBody",
    "descriptionBodyPlain", "additional", "additionalPlain", "opening", "openingPlain",
    "lists", "overview", "basic_qualifications", "preferred_qualifications",
    "description_short", "metadata", "data_compliance", "compensation", "facets",
}


def trim(data: Any) -> Any:
    if isinstance(data, dict):
        # SmartRecruiters' list of postings is called `content`; keep it.
        return {k: trim(v) for k, v in data.items()
                if k not in HEAVY_KEYS or (k == "content" and isinstance(v, list))}
    if isinstance(data, list):
        return [trim(x) for x in data]
    return data


def snapshot_name(url: str, options: dict) -> str:
    digest = hashlib.sha1(json.dumps([url, options], sort_keys=True).encode()).hexdigest()[:12]
    host = urlsplit(url).netloc.replace("www.", "").split(":")[0]
    return f"{host}-{digest}.json.gz"


class RecordingClient:
    def __init__(self, inner, directory: str | Path):
        self.inner = inner
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = inner.name

    @property
    def requests_made(self) -> int:
        return self.inner.requests_made

    def fetch(self, url: str, **options: Any) -> FetchResult:
        result = self.inner.fetch(url, **options)
        record = {
            "url": url, "options": options, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status_code": result.status_code, "final_url": result.final_url, "data": trim(result.data),
        }
        # mtime=0 keeps gzip's own timestamp out of the file, so the bytes depend only on the record.
        blob = json.dumps(record, ensure_ascii=False).encode("utf-8")
        (self.dir / snapshot_name(url, options)).write_bytes(gzip.compress(blob, mtime=0))
        return result


class ReplayClient:
    name = "replay"

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        if not self.dir.is_dir():
            raise FetchError(f"snapshot directory {self.dir} not found", fatal=True)
        self.requests_made = 0

    def fetch(self, url: str, **options: Any) -> FetchResult:
        path = self.dir / snapshot_name(url, options)
        if not path.exists():
            raise FetchError(f"no snapshot for {url} (expected {path.name})")
        self.requests_made += 1
        with gzip.open(path, "rt", encoding="utf-8") as f:
            rec = json.load(f)
        return FetchResult(url=url, status_code=rec["status_code"], data=rec["data"],
                           final_url=rec.get("final_url", url), meta={"fetched_at": rec.get("fetched_at")})
