"""The normalised posting record and the helpers every source shares."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

# Matches "Intern", "Internship", "Co-op" as whole words, so "Internal" and
# "International" don't count.
INTERN_RE = re.compile(r"\b(interns?|internships?|co-?ops?|apprentice(ship)?s?)\b", re.I)

# Roles that mention interns but aren't internships (e.g. "University Recruiter, Interns").
NOT_INTERN_RE = re.compile(r"\b(recruit(er|ing)?|coordinator)\b", re.I)

# Rough "is this a software / technical role" tag, used by `list --tech`.
TECH_RE = re.compile(
    r"\b(software|swe|developer|engineer(ing)?|data|machine learning|ml|ai|research(er)?|"
    r"scientist|science|security|infrastructure|backend|back[- ]end|front[- ]?end|full[- ]?stack|"
    r"platform|devops|sre|quant(itative)?|computer|systems?|cloud|mobile|ios|android|web|"
    r"firmware|embedded|robotics|hardware|fpga|asic|silicon|compiler|gpu|deep learning|"
    r"cyber ?security|it)\b",
    re.I,
)


@dataclass
class Posting:
    company_id: str  # config id, e.g. "stripe"
    company: str  # display name, e.g. "Stripe"
    source: str  # "greenhouse", "lever", ...
    source_id: str  # the job's id on that source; stable across runs
    title: str
    location: str
    url: str  # job page with the apply button
    posted_at: str | None = None  # YYYY-MM-DD, or None when the source doesn't say
    posted_text: str = ""  # original wording when only approximate ("30+ days ago")

    @property
    def key(self) -> str:
        """De-duplication key: one company + the source's own job id."""
        return f"{self.company_id}:{self.source_id}"

    @property
    def is_tech(self) -> bool:
        return bool(TECH_RE.search(self.title))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_tech"] = self.is_tech
        return d


def is_internship(title: str, source_says_intern: bool = False) -> bool:
    """True if the source flags it as an internship, or the title says so."""
    if NOT_INTERN_RE.search(title):
        return False
    return source_says_intern or bool(INTERN_RE.search(title))


def clean(text: str | None) -> str:
    """Collapse whitespace; None -> ''."""
    return re.sub(r"\s+", " ", text or "").strip()


def iso_to_date(value: str | None) -> str | None:
    """'2026-09-03T13:32:53-04:00' -> '2026-09-03' (the date as the source wrote it)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        m = re.match(r"\d{4}-\d{2}-\d{2}", value)
        return m.group(0) if m else None


def epoch_ms_to_date(value: int | float | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()


def text_date_to_date(value: str | None, fmt: str = "%B %d, %Y") -> str | None:
    """'November  5, 2026' -> '2026-11-05'."""
    if not value:
        return None
    try:
        return datetime.strptime(clean(value), fmt).date().isoformat()
    except ValueError:
        return None


def relative_to_date(text: str, today: date) -> str | None:
    """Workday-style 'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago'.
    '30+ Days Ago' is too vague to turn into a date, so it returns None."""
    t = clean(text).lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s+days?\s+ago", t)
    if m and "+" not in t:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return None
