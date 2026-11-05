# intern-radar

Students hunting for software internships check dozens of careers sites, each on
its own site and in its own format. **intern-radar** pulls the current internship
openings from **20 companies** into one normalised list (company, role,
location, posted date, apply link) and shows it as a CLI table, JSON/CSV, or a
small searchable web page.

All fetching goes through [String Web Access](https://portal.usestring.ai/docs/fetch/overview).
A local SQLite database de-duplicates postings across runs, so you can see
**what's new since the last run** and what has closed.

- Read-only: GET requests only (enforced in code), no logins, nothing submitted.
- Polite: one request at a time, at least 1.5 s apart, about 25 requests per full run.
- No dependencies: Python 3.10+ standard library only.

## Quick start (no key needed)

The repo includes a snapshot of a real String run (`snapshot/`), so you can try
everything offline:

```bash
git clone https://github.com/2006-sk/Stringinterview.git && cd Stringinterview
python3 -m internradar scrape --transport replay   # load the snapshot into data/internradar.db
python3 -m internradar list --category software --location "new york"
python3 -m internradar list --format html --out docs/index.html && open docs/index.html
```

## Setup for live data

1. Get a String Web Access key at <https://portal.usestring.ai/api-keys>.
2. `cp .env.example .env` and paste the key into `STRING_API_KEY=`.
3. `python3 -m internradar scrape`

Optional: `pip install -e .` gives you an `intern-radar` command, the same as `python3 -m internradar`.

## How to run

| Command | What it does |
|---|---|
| `scrape` | Fetch all 20 companies through String and update the database. Prints a line per company and lists any new postings. |
| `scrape --company stripe --company nvidia` | Only some companies (ids from `companies.json`). |
| `scrape --record` | Also save the (trimmed) responses to `snapshot/` for offline replay. |
| `scrape --transport replay` | Run the whole pipeline from `snapshot/`: no network, no key. |
| `scrape --transport direct` | Plain GET without String, for people without a key (the NVIDIA source needs String's browser and is skipped). |
| `list` | All open internships, newest first. |
| `new` | Postings first seen in the latest run (that is, new since the run before). |
| `new --closed` | Postings that disappeared from their site in the latest run. |
| `companies` | Each company, its source, open count, and how its last fetch went. |
| `runs` | History of runs: companies ok/failed, new, closed, requests used. |

Filters for `list` and `new`:

```bash
python3 -m internradar list --search "machine learning"      # words in the role title
python3 -m internradar list --location london                 # words in the location
python3 -m internradar list --category software               # software | data | hardware | other
python3 -m internradar list --tech                            # everything except "Business & Other"
python3 -m internradar list --company stripe --company figma
python3 -m internradar list --since 2026-10-01 --sort company --limit 50
python3 -m internradar list --format json   # or csv, html; add --out FILE to write a file
```

Example:

```
  COMPANY   ROLE                                                        LOCATION                      POSTED      APPLY
-----------------------------------------------------------------------------------------------------------------------
  Palantir  Software Engineer, Internship - Sovereign AI Systems        New York, NY                  2026-11-05  https://jobs.lever.co/palantir/cd64bcd4-…
  Figma     PhD Intern, Software Engineer - Interaction Design (2027)   San Francisco, CA • New Yor…  2026-11-04  https://boards.greenhouse.io/figma/jobs/6241542004?…
  NVIDIA    Software Engineering Intern - 2027                          Germany, Munich               2026-11-04  https://nvidia.wd5.myworkdayjobs.com/…_JR2029184
```

### The web page

`list --format html --out docs/index.html` writes one self-contained file, with
the postings embedded and a little inline JavaScript. It works from disk or any
static host (e.g. GitHub Pages from `/docs`). It has:

- **word search** over company, role and location: every word must match, `"quoted phrases"` work, and `-word` excludes (e.g. `software london -phd`); matches are highlighted.
- filters for company, role category (with counts), posted within 7/30/90 days, and new since the last run.
- sortable columns (click a header), with undated postings always last.
- the filters are kept in the URL, so a filtered view can be shared; press `/` to jump to search.

## What's covered

20 companies, chosen to cover the main applicant-tracking systems (ATS) plus a few custom careers sites.
Numbers are from the live run on 2026-11-05.

| Company | Source | How String fetches it | Jobs scanned | Internships |
|---|---|---|---:|---:|
| Stripe | Greenhouse board API | plain request | 763 | 19 |
| Databricks | Greenhouse | plain request | 923 | 13 |
| Figma | Greenhouse | plain request | 143 | 9 |
| Coinbase | Greenhouse | plain request | 278 | 27 |
| Cloudflare | Greenhouse | plain request | 463 | 6 |
| Pinterest | Greenhouse | plain request | 165 | 13 |
| Datadog | Greenhouse | plain request | 396 | 6 |
| Lyft | Greenhouse | plain request | 167 | 23 |
| Waymo | Greenhouse | plain request | 367 | 61 |
| SpaceX | Greenhouse | plain request | 2,890 | 16 |
| Anduril | Greenhouse | plain request | 2,572 | 39 |
| Jump Trading | Greenhouse | plain request | 93 | 28 |
| Palantir | Lever postings API | plain request | 308 | 50 |
| Notion | Ashby job-board API | plain request | 150 | 2 |
| Ramp | Ashby | plain request | 170 | 5 |
| Cohere | Ashby | plain request | 118 | 3 |
| ServiceNow | SmartRecruiters API (paginated) | plain request ×2 | 183 | 7 |
| Amazon | amazon.jobs search JSON (paginated) | plain request ×5 | 469 | 459 |
| Jane Street | janestreet.com jobs JSON | plain request | 219 | 41 |
| NVIDIA | Workday careers site | **browser render → Markdown** | 20 | 19 |
| **Total** | | **25 requests** | **~10,800** | **846** |

By role category: Software 166 · Data & Research 159 · Hardware & Engineering 87 · Business & Other 434.

**Adding a company** that uses Greenhouse, Lever, Ashby, SmartRecruiters or Workday is a
one-line change to `companies.json`, e.g. `{"id": "airbnb", "name": "Airbnb", "source": "greenhouse", "board": "airbnb"}`.
`scripts/probe.py greenhouse:airbnb lever:somecompany` checks whether a board exists and how many internships it has.

## How it works (data flow)

```
companies.json ──► pipeline.scrape() ── for each company ──────────────────────────────┐
                        │                                                              │
                        ▼                                                              │
             sources/<ats>.fetch(cfg)  builds the URL(s) for that company's careers data
                        │
                        ▼
        StringClient.fetch(url)  ─── POST https://request.usestring.ai/v1/fetch {"url": ...}
           GET only · 1.5 s pacing · retries 429/5xx (honours Retry-After)
           401/402 stop the run · 403/404 fail just that company
           (optional) RecordingClient saves the response to snapshot/  ◄── ReplayClient reads it back
                        │
                        ▼
             sources/<ats>.parse(data)   source-specific JSON / Markdown → Posting
                        │                 (company, title, location, url, posted_at, source job id)
                        ▼
             models.is_internship()      source's own flag (Lever "Internship", Ashby "Intern",
                        │                Jane Street availability) OR title match in 9 languages
                        ▼
             db.save_company()           SQLite upsert keyed by company + source job id
                        │                 new = first seen this run · closed = missing this run
                        ▼
             list / new / companies / runs  ──► table · JSON · CSV · HTML (render.py)
```

**De-duplication.** A posting's key is `company id + the source's own job id`
(Greenhouse id, Lever/Ashby UUID, Amazon req id, NVIDIA `JR…` number), not
title or URL, which carry tracking parameters. Seeing the same key again
updates it in place; it's never added twice. Two postings with the same title
and city but different requisition ids are different roles, and both are kept.

**New and closed.** Every scrape is a row in `runs`. A posting is *new* if it
was first seen in the latest run. It is *closed* when its company was fetched
**completely** but the posting wasn't there. If any page of a company fails, that
company is logged as failed and none of its postings are touched, so a network
blip can't make everything look closed. A closed posting that comes back is reopened, not counted as new.

**Tables:** `runs` (one per scrape, with totals and requests used), `postings`
(one per job: `first_seen_run`, `last_seen_run`, `active`, `closed_run`), `fetch_log` (per company per run: ok/error, jobs scanned, internships, requests, duration).

**Normalised record** (`list --format json`):

```json
{"company": "Stripe", "title": "Data Analyst, Intern", "location": "Toronto",
 "posted_at": "2026-10-01", "posted_text": null, "url": "https://stripe.com/jobs/search?gh_jid=8194287",
 "category": "Data & Research", "source": "greenhouse", "first_seen_at": "2026-11-05T19:51:05+00:00",
 "active": true, "new": false}
```

`posted_at` is the date the source publishes (Greenhouse `first_published`,
Lever `createdAt`, Ashby `publishedAt`, SmartRecruiters `releasedDate`, Amazon
`posted_date`, Workday "Posted N Days Ago"). It is `null` when the source gives none.

## Tests

```bash
python3 -m unittest discover -s tests -t .     # 79 tests, about 1 s, no network
```

| File | Covers |
|---|---|
| `test_models.py` | internship filter (incl. the regressions below and non-English titles), role categories, date parsing |
| `test_sources.py` | every parser against fixtures cut from real responses; pagination; request options |
| `test_http.py` | `StringClient` against a local fake String server: JSON / Markdown / jsonSchema bodies, 429 retry with `Retry-After`, fatal 401/402, the KYC 403, the GET-only guard, pacing |
| `test_db.py` | new → closed → reopened across runs, per-company closing, every query filter, schema migration |
| `test_snapshot.py` | record → replay round trip, trimming, gzip without timestamps |
| `test_render.py` | table/JSON/CSV/HTML, `</script>` injection in a title, `node --check` on the page's JavaScript |
| `test_pipeline.py` | the connected pipeline over several runs; a failed company keeps its postings; a fatal error stops the run; a parser bug in one source doesn't sink the others |
| `test_e2e.py` | the CLI end to end on the committed snapshot: scrape, filters, JSON shape, HTML, second run = 0 new, error handling |

The live path was also run end to end against String twice (20/20 companies, 25 requests each), and one apply link per source was opened to confirm it lands on the right job page.

## Known gaps

- **NVIDIA (Workday) is first page only:** 20 of about 1,100 search results. Workday loads further pages through its own API calls, which would mean scripting String's browser to click "next". The first page is ranked by relevance to "intern", so it is mostly internships.
- **Posted dates can be old or missing.** Some companies keep "evergreen" postings open for years (26 Palantir postings say 2016–2025, 10 at Databricks). The date shown is the source's own. Jane Street publishes no dates (shown as `—`), and Workday's "30+ days ago" is kept as text.
- **Amazon dominates the count** (459 of 846) because amazon.jobs lists every country and every requisition separately. Filter with `--company`, `--location` or `--category`.
- **Categories are keyword rules** on the title, so expect some misses (e.g. "Technical Program Manager" counts as Business & Other).
- **Search-based sources** (Amazon, ServiceNow, NVIDIA) only see postings their own search returns for "intern", and Amazon is capped at 5 pages (500 results).
- **No descriptions, pay, or deadlines**: just the five normalised fields plus category.
- **Live runs depend on your String plan.** The snapshot in the repo is from 2026-11-05.

## What broke while building it

1. **An exclusion rule silently dropped real internships.** To skip jobs like
   "University Recruiter, Interns" I excluded titles containing "recruit" or
   "coordinator". Auditing the titles the filter rejected from Amazon's *intern*
   search showed it had thrown away "2027 Applied Science Internship – Computer
   Vision, PhD Student Science **Recruiting**" (Amazon appends team names), "Area Manager Intern… University
   Recruiting", and "Facilities Coordinator Intern". The same audit found German
   "Praktikum" and French "Stagiaire" roles that an English-only regex missed.
   After narrowing the rule and adding the non-English terms, **32 real internships were recovered and none lost**
   across 10,840 titles. Regression tests now pin this down (`tests/test_models.py`).
2. **AI extraction invented apply links.** I tried String's `jsonSchema`
   extraction on Google Careers as a "works on any site" fallback. Titles came
   back right, but 19 of 20 jobs got the *same* URL, and locations were dropped.
   A wrong apply link is worse than no listing, so every source here uses a
   deterministic parser over structured data instead.
3. **String's Markdown responses aren't JSON.** With `format: "json"` String
   wraps the page in an envelope (`{statusCode, data, finalUrl}`), but with
   `format: "markdown"` the body *is* the Markdown and the status moves to the
   `x-status-code` header. The first client assumed JSON everywhere and crashed
   on the NVIDIA page. With `jsonSchema` the extracted object is the whole body. Fixed in `internradar/http.py`, covered by `tests/test_http.py`.
4. **Write requests are blocked on this key until KYC.** While exploring, a
   `POST` through `/fetch` returned 403 "blocked pending KYC", and a form submit in
   String's remote browser failed with `ERR_ACCESS_DENIED`. This tool never needs
   to write, so it is GET-only by design, and the client refuses non-GET methods before sending anything.
5. Smaller ones: `Retry-After: 0` made the client wait 2 s (`0` is falsy in
   Python); gzip stamps the current time into every file, which made snapshot
   diffs noisy (now written with `mtime=0`).

## What I'd do with another day

- **Workday pagination** via String browser actions (click "next", `waitForResponse` on Workday's jobs API, `captureXHR` to read the JSON), and add more Workday companies (Salesforce, Adobe, Intel).
- **Scheduled runs**: a GitHub Action every few hours that scrapes, commits the snapshot, and publishes `docs/index.html` to GitHub Pages, so "new since last run" becomes a real feed (RSS or email digest).
- **More sources**: Google, Microsoft and Apple have custom careers sites; each needs its own adapter (deterministic, see "What broke" #2).
- **Better classification**: use the Claude API to tag role, degree level (BS/MS/PhD), season (Summer 2027), and remote/hybrid. Validate the output against the source data, never trust it for links.
- **Detail pages** for deadlines and pay, fetched only for new postings to keep requests low.

## Project layout

```
internradar/
  cli.py          commands and output
  pipeline.py     one scrape run: fetch → parse → filter → store
  http.py         StringClient (String Web Access) and DirectClient
  snapshot.py     record responses / replay offline
  sources/        one adapter per source: greenhouse, lever, ashby, smartrecruiters, amazon, janestreet, workday
  models.py       Posting record, internship filter, role categories, date helpers
  db.py           SQLite schema, upsert, new/closed, queries
  render.py       table, JSON, CSV, HTML page
companies.json    the 20 companies
snapshot/         gzipped responses from the last recorded live run
docs/index.html   the generated web page
scripts/probe.py  check whether a job board exists and has internships
tests/            79 offline tests + fixtures cut from real responses
```
