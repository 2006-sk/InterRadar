# intern-radar

Pulls current **internship openings** from 20 company careers sites into one
normalised list (company, role, location, posted date, apply link), using
[String Web Access](https://portal.usestring.ai/docs/fetch/overview) to do the
fetching. A local SQLite database de-duplicates postings across runs, so you can
see **what's new since the last run** and what has closed.

> Status: work in progress, built on 2026-11-05. This README is updated as the
> project is built.

## Setup

_TODO_

## How to run

_TODO_

## What's covered

_TODO_

## How it works (data flow)

_TODO_

## Known gaps

_TODO_

## What broke while building it

1. **String's Markdown responses aren't JSON.** With `format: "json"` String
   wraps the page in an envelope (`{statusCode, data, finalUrl}`), but with
   `format: "markdown"` the body *is* the Markdown and the status moves to the
   `x-status-code` header. The first client assumed JSON everywhere and crashed
   on the NVIDIA page. The same thing happens with `jsonSchema`: the extracted
   object is the whole body. Fixed in `internradar/http.py`.
2. **AI extraction invented apply links.** I tried String's `jsonSchema`
   extraction on Google Careers as a "works on any site" fallback. Titles came
   back right, but 19 of 20 jobs got the *same* URL, and locations were
   dropped. A wrong apply link is worse than no listing, so every source here
   uses a deterministic parser over structured data instead.
