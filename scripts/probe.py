"""Probe candidate job boards through String and report which ones work.

Used once to choose the companies in companies.json. Saves each raw response
to data/raw/ so parsers can be developed without spending more credits.

    python scripts/probe.py greenhouse:stripe lever:palantir ashby:openai ...
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from internradar.http import FetchError, StringClient, load_dotenv  # noqa: E402

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{t}/postings?q=intern&limit=100",
}
INTERN = re.compile(r"\b(intern|interns|internship|internships|co-?op)\b", re.I)


def titles(kind, data):
    if kind == "greenhouse":
        return [j["title"] for j in data.get("jobs", [])]
    if kind == "lever":
        return [j["text"] for j in data] if isinstance(data, list) else []
    if kind == "ashby":
        return [j["title"] for j in data.get("jobs", [])]
    if kind == "smartrecruiters":
        return [j["name"] for j in data.get("content", [])]
    return []


def main(specs):
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    import os
    client = StringClient(os.environ.get("STRING_API_KEY", ""), min_interval=1.5)
    out = root / "data" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    for spec in specs:
        kind, token = spec.split(":", 1)
        url = URLS[kind].format(t=token)
        try:
            r = client.fetch(url)
        except FetchError as e:
            print(f"{spec:40} ERROR {e}")
            if e.fatal:
                break
            continue
        (out / f"{kind}_{token}.json").write_text(json.dumps(r.data))
        ts = titles(kind, r.data) if isinstance(r.data, (dict, list)) else []
        hits = [t for t in ts if INTERN.search(t)]
        print(f"{spec:40} HTTP {r.status_code} {r.billed_type:16} jobs={len(ts):4} intern={len(hits):3}  "
              f"e.g. {hits[0][:60] if hits else '-'}")
    print(f"String requests made: {client.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])
