"""Output formats: terminal table, JSON, CSV, and a single self-contained HTML page."""

from __future__ import annotations

import csv
import html
import io
import json
import shutil

FIELDS = ["company", "title", "location", "posted", "url"]


def posted_label(row: dict) -> str:
    return row.get("posted_at") or row.get("posted_text") or "—"


def public_rows(rows: list[dict], new_run: int | None = None) -> list[dict]:
    """The normalised record the brief asks for, plus a few useful extras."""
    out = []
    for r in rows:
        out.append({
            "company": r["company"], "title": r["title"], "location": r["location"],
            "posted_at": r["posted_at"], "posted_text": r["posted_text"] or None, "url": r["url"],
            "is_tech": bool(r["is_tech"]), "source": r["source"],
            "first_seen_at": r["first_seen_at"], "active": bool(r["active"]),
            "new": new_run is not None and r["first_seen_run"] == new_run,
        })
    return out


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)] + "…"


def table(rows: list[dict], new_run: int | None = None, show_url: bool = True) -> str:
    """Fixed-width table. ROLE and LOCATION are truncated to fit; the apply link
    goes last and is never truncated, so it stays clickable."""
    if not rows:
        return "(no postings match)"
    data = [[("* " if new_run is not None and r["first_seen_run"] == new_run else "  ") + r["company"],
             r["title"], r["location"], posted_label(r)] for r in rows]
    headers = ["  COMPANY", "ROLE", "LOCATION", "POSTED"]
    widths = [max(len(h), *(len(d[i]) for d in data)) for i, h in enumerate(headers)]
    if not show_url:
        # Use the whole terminal for ROLE and LOCATION.
        term = shutil.get_terminal_size((120, 20)).columns
        room = max(term - widths[0] - widths[3] - 6, 40)
        widths[1] = min(widths[1], int(room * 0.65))
        widths[2] = min(widths[2], room - widths[1])
    else:
        widths[1], widths[2] = min(widths[1], 58), min(widths[2], 28)
    head = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    lines = [head + ("  APPLY" if show_url else ""), "-" * (len(head) + (7 if show_url else 0))]
    for d, r in zip(data, rows):
        line = "  ".join(_cut(v, w).ljust(w) for v, w in zip(d, widths))
        lines.append((line + "  " + r["url"]) if show_url else line.rstrip())
    return "\n".join(lines)


def to_json(rows: list[dict], new_run: int | None = None) -> str:
    return json.dumps(public_rows(rows, new_run), indent=2, ensure_ascii=False)


def to_csv(rows: list[dict], new_run: int | None = None) -> str:
    buf = io.StringIO()
    pub = public_rows(rows, new_run)
    writer = csv.DictWriter(buf, fieldnames=list(pub[0].keys()) if pub else ["company"])
    writer.writeheader()
    writer.writerows(pub)
    return buf.getvalue()


def to_html(rows: list[dict], new_run: int | None = None, generated_at: str = "", companies: int = 0) -> str:
    pub = public_rows(rows, new_run)
    body = []
    for r in pub:
        badge = '<span class="new">NEW</span> ' if r["new"] else ""
        posted = r["posted_at"] or r["posted_text"] or "—"
        body.append(
            f'<tr data-tech="{int(r["is_tech"])}" data-new="{int(r["new"])}">'
            f"<td>{html.escape(r['company'])}</td>"
            f"<td>{badge}{html.escape(r['title'])}</td>"
            f"<td>{html.escape(r['location'])}</td>"
            f'<td class="d">{html.escape(posted)}</td>'
            f'<td><a href="{html.escape(r["url"], quote=True)}" target="_blank" rel="noopener">Apply ↗</a></td></tr>')
    new_count = sum(r["new"] for r in pub)
    return PAGE.format(rows="\n".join(body), total=len(pub), new=new_count,
                       generated=html.escape(generated_at), companies=companies)


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>intern-radar: internship openings</title>
<style>
  :root {{ color-scheme: light dark; --line: #8884; --muted: #888; --accent: #2f6fdf; }}
  body {{ font: 14px/1.45 system-ui, -apple-system, sans-serif; margin: 2rem auto; max-width: 1200px; padding: 0 1rem; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 .25rem; }}
  p.meta {{ color: var(--muted); margin: 0 0 1rem; }}
  .controls {{ display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; margin-bottom: 1rem; }}
  input[type=search] {{ flex: 1; min-width: 220px; padding: .45rem .6rem; border: 1px solid var(--line); border-radius: 6px; font: inherit; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ cursor: pointer; user-select: none; white-space: nowrap; position: sticky; top: 0; background: Canvas; }}
  td.d {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
  a {{ color: var(--accent); white-space: nowrap; }}
  .new {{ background: #1f9d55; color: #fff; border-radius: 4px; padding: 0 .35rem; font-size: .75rem; font-weight: 600; }}
  #count {{ color: var(--muted); }}
</style></head>
<body>
<h1>Internship openings</h1>
<p class="meta">{total} open internships from {companies} companies · {new} new since the previous run · generated {generated} by
<a href="https://github.com/2006-sk/intern-radar">intern-radar</a>, fetched through String Web Access.</p>
<div class="controls">
  <input type="search" id="q" placeholder="Filter by company, role or location (e.g. software, london, stripe)">
  <label><input type="checkbox" id="tech"> Technical roles only</label>
  <label><input type="checkbox" id="onlynew"> New only</label>
  <span id="count"></span>
</div>
<table id="t"><thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Posted</th><th>Link</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<script>
const rows = [...document.querySelectorAll('#t tbody tr')];
const q = document.getElementById('q'), tech = document.getElementById('tech'), onlynew = document.getElementById('onlynew');
function apply() {{
  const terms = q.value.toLowerCase().split(/\\s+/).filter(Boolean); let n = 0;
  for (const r of rows) {{
    const text = r.textContent.toLowerCase();
    const show = terms.every(t => text.includes(t)) && (!tech.checked || r.dataset.tech === '1') && (!onlynew.checked || r.dataset.new === '1');
    r.hidden = !show; n += show;
  }}
  document.getElementById('count').textContent = n + ' shown';
}}
[q, tech, onlynew].forEach(el => el.addEventListener('input', apply));
document.querySelectorAll('#t th').forEach((th, i) => th.addEventListener('click', () => {{
  const dir = th.dataset.dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
  rows.sort((a, b) => a.cells[i].textContent.localeCompare(b.cells[i].textContent) * (dir === 'asc' ? 1 : -1));
  rows.forEach(r => r.parentNode.appendChild(r));
}}));
apply();
</script>
</body></html>
"""
