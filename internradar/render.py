"""Output formats: terminal table, JSON, CSV, and a single self-contained HTML page."""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections import Counter

from .models import CATEGORIES, categorize


def posted_label(row: dict) -> str:
    return row.get("posted_at") or row.get("posted_text") or "—"


def public_rows(rows: list[dict], new_run: int | None = None) -> list[dict]:
    """The normalised record the brief asks for, plus a few useful extras."""
    out = []
    for r in rows:
        out.append({
            "company": r["company"], "title": r["title"], "location": r["location"],
            "posted_at": r["posted_at"], "posted_text": r["posted_text"] or None, "url": r["url"],
            "category": r.get("category") or categorize(r["title"]), "source": r["source"],
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


def to_html(rows: list[dict], new_run: int | None = None, generated_at: str = "") -> str:
    """One static file: the postings are embedded as JSON and a small script does
    the searching, filtering and sorting in the browser. No dependencies."""
    pub = public_rows(rows, new_run)
    compact = [{"c": r["company"], "t": r["title"], "l": r["location"], "p": r["posted_at"],
                "pt": r["posted_text"], "u": r["url"], "k": r["category"], "n": r["new"]} for r in pub]
    meta = {
        "generated": generated_at,
        "dataDate": (generated_at or "")[:10],
        "hasPreviousRun": new_run is not None,
        "companies": sorted(Counter(r["company"] for r in pub).items(), key=lambda kv: kv[0].lower()),
        "categories": [[c, sum(r["category"] == c for r in pub)] for c in CATEGORIES],
    }
    # "</" inside a <script> block would end it early; JSON allows "<\/" as an escape.
    blob = json.dumps({"meta": meta, "rows": compact}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.replace("__DATA__", blob)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internship openings · intern-radar</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #e5e5ea; --soft: #f5f5f7;
    --accent: #0a66c2; --accent-soft: #e8f1fb; --new: #1a7f37; --new-soft: #dafbe1;
    --sw: #0a66c2; --data: #8250df; --hw: #bc4c00; --other: #6e6e73;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #111113; --fg: #ececf1; --muted: #9a9aa3; --line: #2a2a2f; --soft: #1b1b1f;
      --accent: #4c9aff; --accent-soft: #14263d; --new: #3fb950; --new-soft: #12301b;
      --sw: #4c9aff; --data: #b392f0; --hw: #f0883e; --other: #9a9aa3;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 1240px; margin: 0 auto; padding: 32px 20px 64px; }
  header h1 { font-size: 24px; font-weight: 650; letter-spacing: -0.01em; margin: 0 0 4px; }
  header p { margin: 0; color: var(--muted); }
  header a { color: var(--accent); text-decoration: none; }

  .controls { position: sticky; top: 0; z-index: 2; background: var(--bg); padding: 16px 0 12px;
              border-bottom: 1px solid var(--line); margin-top: 20px; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .row + .row { margin-top: 10px; }
  .search { flex: 1 1 320px; position: relative; }
  .search input { width: 100%; padding: 10px 12px 10px 36px; font: inherit; color: var(--fg);
                  background: var(--soft); border: 1px solid var(--line); border-radius: 10px; outline: none; }
  .search input:focus { border-color: var(--accent); background: var(--bg); }
  .search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--muted); }
  .search kbd { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font: 12px ui-monospace, monospace;
                color: var(--muted); border: 1px solid var(--line); border-radius: 5px; padding: 0 5px; }
  select { font: inherit; color: var(--fg); background: var(--soft); border: 1px solid var(--line);
           border-radius: 10px; padding: 9px 10px; max-width: 220px; }
  .chip { font: inherit; font-size: 13px; color: var(--fg); background: var(--soft); border: 1px solid var(--line);
          border-radius: 999px; padding: 5px 12px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
  .chip .dot { width: 8px; height: 8px; border-radius: 50%; }
  .chip .count { color: var(--muted); font-variant-numeric: tabular-nums; }
  .chip[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
  .toggle { display: inline-flex; gap: 6px; align-items: center; color: var(--muted); cursor: pointer; user-select: none; }
  .spacer { flex: 1; }
  .summary { color: var(--muted); font-variant-numeric: tabular-nums; }
  button.link { font: inherit; background: none; border: 0; color: var(--accent); cursor: pointer; padding: 0; }

  table { width: 100%; border-collapse: collapse; margin-top: 4px; }
  th { text-align: left; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase;
       letter-spacing: .04em; padding: 12px 10px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable:hover { color: var(--fg); }
  th .arrow { display: inline-block; width: 1em; color: var(--accent); }
  td { padding: 11px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  tbody tr:hover { background: var(--soft); }
  td.company { font-weight: 600; white-space: nowrap; }
  td.role .title { font-weight: 500; }
  td.role .tags { margin-top: 3px; display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { font-size: 11.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; border: 1px solid currentColor; opacity: .9; }
  .tag.new { color: var(--new); background: var(--new-soft); border-color: transparent; }
  td.loc { color: var(--muted); max-width: 300px; }
  td.posted { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted); }
  td.apply a { display: inline-block; white-space: nowrap; color: var(--accent); text-decoration: none; font-weight: 600;
               border: 1px solid var(--line); border-radius: 8px; padding: 4px 10px; }
  td.apply a:hover { border-color: var(--accent); background: var(--accent-soft); }
  mark { background: #fff2a8; color: inherit; border-radius: 2px; }
  @media (prefers-color-scheme: dark) { mark { background: #5c4a00; } }
  .empty { text-align: center; color: var(--muted); padding: 48px 0; }
  footer { margin-top: 28px; color: var(--muted); font-size: 12.5px; }
  @media (max-width: 760px) {
    th.h-loc, td.loc { display: none; }
    td.company { white-space: normal; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Internship openings</h1>
    <p id="headline"></p>
  </header>

  <div class="controls">
    <div class="row">
      <label class="search">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="5.25" stroke="currentColor" stroke-width="1.5"/><path d="M11 11l3.5 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
        <input id="q" type="search" autocomplete="off" spellcheck="false"
               placeholder='Search words: software london   ·   "machine learning"   ·   -phd to exclude'
               aria-label="Search by words in company, role or location">
        <kbd>/</kbd>
      </label>
      <select id="company" aria-label="Company"></select>
      <select id="posted" aria-label="Posted">
        <option value="">Posted: any time</option>
        <option value="7">Posted: last 7 days</option>
        <option value="30">Posted: last 30 days</option>
        <option value="90">Posted: last 90 days</option>
      </select>
    </div>
    <div class="row">
      <div id="cats" class="row" style="margin:0"></div>
      <label class="toggle" id="newWrap"><input type="checkbox" id="onlyNew"> New since last run</label>
      <span class="spacer"></span>
      <span class="summary" id="summary"></span>
      <button class="link" id="reset" type="button">Reset</button>
    </div>
  </div>

  <table>
    <thead><tr>
      <th class="sortable" data-key="c">Company <span class="arrow"></span></th>
      <th class="sortable" data-key="t">Role <span class="arrow"></span></th>
      <th class="sortable h-loc" data-key="l">Location <span class="arrow"></span></th>
      <th class="sortable" data-key="p">Posted <span class="arrow"></span></th>
      <th></th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div class="empty" id="empty" hidden>No internships match these filters. <button class="link" id="reset2" type="button">Clear filters</button></div>

  <footer>
    Built with <a href="https://github.com/2006-sk/Stringinterview">intern-radar</a>. Data fetched read-only through
    String Web Access from each company's public careers site. Always check the posting on the company's own site before applying.
  </footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(() => {
  const { meta, rows } = JSON.parse(document.getElementById('data').textContent);
  const $ = (id) => document.getElementById(id);
  const CAT_COLORS = { 'Software': 'var(--sw)', 'Data & Research': 'var(--data)',
                       'Hardware & Engineering': 'var(--hw)', 'Business & Other': 'var(--other)' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  rows.forEach((r) => { r.hay = (r.c + ' ' + r.t + ' ' + r.l).toLowerCase(); });

  // ---- state (mirrored in the URL so a filtered view can be shared) ----
  const state = { q: '', company: '', posted: '', cats: new Set(), onlyNew: false, sort: 'p', dir: -1 };
  const params = new URLSearchParams(location.search);
  state.q = params.get('q') || '';
  state.company = params.get('company') || '';
  state.posted = params.get('posted') || '';
  (params.get('cat') || '').split(',').filter(Boolean).forEach((c) => state.cats.add(c));
  state.onlyNew = params.get('new') === '1';
  if (params.get('sort')) { state.sort = params.get('sort'); state.dir = params.get('dir') === 'asc' ? 1 : -1; }

  function syncUrl() {
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.company) p.set('company', state.company);
    if (state.posted) p.set('posted', state.posted);
    if (state.cats.size) p.set('cat', [...state.cats].join(','));
    if (state.onlyNew) p.set('new', '1');
    if (state.sort !== 'p' || state.dir !== -1) { p.set('sort', state.sort); p.set('dir', state.dir === 1 ? 'asc' : 'desc'); }
    const qs = p.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
  }

  // ---- word search: every word must match; "quoted phrases" and -excluded words ----
  function parseQuery(q) {
    const include = [], exclude = [];
    for (const m of q.toLowerCase().matchAll(/(-?)"([^"]+)"|(-?)(\S+)/g)) {
      const neg = m[1] || m[3], term = (m[2] || m[4] || '').trim();
      if (!term || term === '-') continue;
      (neg ? exclude : include).push(term);
    }
    return { include, exclude };
  }
  function highlight(text, terms) {
    text = String(text ?? '');
    if (!terms.length) return esc(text);
    // Split the raw text on the search terms (odd pieces are matches), then escape each piece.
    const re = new RegExp('(' + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'ig');
    return text.split(re).map((part, i) => (i % 2 ? '<mark>' + esc(part) + '</mark>' : esc(part))).join('');
  }

  // ---- controls ----
  $('headline').innerHTML =
    `<strong>${rows.length}</strong> open internships from <strong>${meta.companies.length}</strong> companies` +
    (meta.hasPreviousRun ? ` · <strong>${rows.filter((r) => r.n).length}</strong> new since the previous run` : '') +
    (meta.generated ? ` · updated ${esc(meta.generated.replace('T', ' ').replace('+00:00', ' UTC'))}` : '');

  $('company').innerHTML = `<option value="">All companies (${meta.companies.length})</option>` +
    meta.companies.map(([c, n]) => `<option value="${esc(c)}">${esc(c)} (${n})</option>`).join('');

  $('cats').innerHTML = meta.categories.map(([c, n]) =>
    `<button type="button" class="chip" data-cat="${esc(c)}" aria-pressed="false">` +
    `<span class="dot" style="background:${CAT_COLORS[c]}"></span>${esc(c)} <span class="count">${n}</span></button>`).join('');

  if (!meta.hasPreviousRun) $('newWrap').hidden = true;

  function setControls() {
    $('q').value = state.q; $('company').value = state.company; $('posted').value = state.posted;
    $('onlyNew').checked = state.onlyNew;
    document.querySelectorAll('.chip').forEach((b) => b.setAttribute('aria-pressed', state.cats.has(b.dataset.cat)));
    document.querySelectorAll('th.sortable').forEach((th) => {
      th.querySelector('.arrow').textContent = th.dataset.key === state.sort ? (state.dir === 1 ? '↑' : '↓') : '';
      th.setAttribute('aria-sort', th.dataset.key === state.sort ? (state.dir === 1 ? 'ascending' : 'descending') : 'none');
    });
  }

  // ---- filter + sort + render ----
  function cutoff(days) {
    if (!days) return null;
    const d = meta.dataDate ? new Date(meta.dataDate + 'T00:00:00Z') : new Date();
    d.setUTCDate(d.getUTCDate() - Number(days));
    return d.toISOString().slice(0, 10);
  }
  function render() {
    const { include, exclude } = parseQuery(state.q);
    const since = cutoff(state.posted);
    const list = rows.filter((r) =>
      include.every((t) => r.hay.includes(t)) && !exclude.some((t) => r.hay.includes(t)) &&
      (!state.company || r.c === state.company) &&
      (!state.cats.size || state.cats.has(r.k)) &&
      (!since || (r.p && r.p >= since)) &&
      (!state.onlyNew || r.n));
    const k = state.sort, dir = state.dir;
    list.sort((a, b) => {
      const x = a[k] || '', y = b[k] || '';
      if (!x !== !y) return x ? -1 : 1;             // empty values always last
      const c = k === 'p' ? (x < y ? -1 : x > y ? 1 : 0) : x.localeCompare(y, undefined, { sensitivity: 'base' });
      return c * dir || a.c.localeCompare(b.c) || a.t.localeCompare(b.t);
    });
    $('rows').innerHTML = list.map((r) => `<tr>
      <td class="company">${highlight(r.c, include)}</td>
      <td class="role"><div class="title">${highlight(r.t, include)}</div><div class="tags">` +
        (r.n ? '<span class="tag new">NEW</span>' : '') +
        `<span class="tag" style="color:${CAT_COLORS[r.k]}">${esc(r.k)}</span></div></td>
      <td class="loc">${highlight(r.l || '—', include)}</td>
      <td class="posted" title="${r.p ? '' : 'The source does not publish an exact date'}">${esc(r.p || r.pt || '—')}</td>
      <td class="apply"><a href="${esc(r.u)}" target="_blank" rel="noopener noreferrer">Apply ↗</a></td>
    </tr>`).join('');
    $('empty').hidden = list.length > 0;
    $('summary').textContent = list.length === rows.length ? `${rows.length} roles` : `${list.length} of ${rows.length} roles`;
    setControls();
    syncUrl();
  }

  // ---- events ----
  let timer;
  $('q').addEventListener('input', (e) => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value; render(); }, 80); });
  $('company').addEventListener('change', (e) => { state.company = e.target.value; render(); });
  $('posted').addEventListener('change', (e) => { state.posted = e.target.value; render(); });
  $('onlyNew').addEventListener('change', (e) => { state.onlyNew = e.target.checked; render(); });
  $('cats').addEventListener('click', (e) => {
    const b = e.target.closest('.chip'); if (!b) return;
    state.cats.has(b.dataset.cat) ? state.cats.delete(b.dataset.cat) : state.cats.add(b.dataset.cat);
    render();
  });
  document.querySelectorAll('th.sortable').forEach((th) => th.addEventListener('click', () => {
    if (state.sort === th.dataset.key) state.dir = -state.dir;
    else { state.sort = th.dataset.key; state.dir = th.dataset.key === 'p' ? -1 : 1; }
    render();
  }));
  const reset = () => { Object.assign(state, { q: '', company: '', posted: '', onlyNew: false, sort: 'p', dir: -1 }); state.cats.clear(); render(); };
  $('reset').addEventListener('click', reset);
  $('reset2').addEventListener('click', reset);
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== $('q')) { e.preventDefault(); $('q').focus(); }
    if (e.key === 'Escape' && document.activeElement === $('q')) { state.q = ''; render(); }
  });
  render();
})();
</script>
</body>
</html>
"""
