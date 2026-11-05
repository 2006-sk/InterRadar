"""The normalised posting record and the helpers every source shares."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

# Matches "Intern", "Internship", "Co-op" as whole words, so "Internal" and
# "International" don't count. Includes the common non-English terms seen on
# these sites (German Praktikum/Werkstudent, French apprenti(e)/stagiaire, ...).
INTERN_RE = re.compile(
    r"\b(interns?|internships?|co-?ops?|apprentice(ship)?s?|apprenti(?:\(e\)|e|es|s)?|"
    r"praktikum|praktikant(in|en)?|werkstudent(in)?|working students?|stagiaire|"
    r"pr[aá]cticas|becari[oa]s?|tirocin(io|ante)|est[aá]gi(o|[aá]rio|[aá]ria)|stagiair)\b",
    re.I,
)

# Jobs *about* interns rather than internships: "University Recruiter, Interns",
# "Internship Program Manager". Kept narrow on purpose: a broad "recruit|coordinator"
# rule dropped real roles like "Applied Science Internship ..., PhD Student Science
# Recruiting" and "Facilities Coordinator Intern" (see README, "What broke").
NOT_INTERN_RE = re.compile(
    r"\binterns?(hip)?s? program (manager|coordinator|lead|director|specialist)\b|"
    r"\b(recruiter|coordinator|manager)\s*[,\-–(:]\s*(early careers? )?(interns|internships)\b",
    re.I,
)

# Role categories, used by `list --category` / `--tech` and the HTML page.
# Checked in order; the first match wins. Words like "cloud", "security" or
# "developer" are too weak on their own ("Business Developer", "Program Manager,
# AWS Cloud"), so business-role words win unless a strong technical word is present.
SOFTWARE, DATA, HARDWARE, OTHER = "Software", "Data & Research", "Hardware & Engineering", "Business & Other"
CATEGORIES = (SOFTWARE, DATA, HARDWARE, OTHER)
_W = lambda pattern: re.compile(rf"\b({pattern})\b", re.I)  # noqa: E731
SOFTWARE_RE = _W(r"software|swe|sde|full[- ]?stack|front[- ]?end|back[- ]?end|mobile|ios|android|"
                 r"devops|sre|site reliability|compilers?|forward deployed|(cyber ?)?security engineer(ing)?|"
                 r"cyber ?security|infrastructure engineer(ing)?|platform engineer(ing)?|it engineer|"
                 r"web developer|application developer|software developer|programmer|logiciels?|d[ée]veloppeur")
DATA_STRONG_RE = _W(r"machine learning|deep learning|data scien\w*|data engineer(ing)?|research(er)?|"
                    r"scientists?|quant(itative)?|computer vision|nlp|applied scien\w*|algorithms?")
HARDWARE_STRONG_RE = _W(r"hardware|asic|fpga|silicon|firmware|embedded|electrical|mechanical|manufacturing|"
                        r"robotics|propulsion|avionics|gpu|vlsi|dft|verification|chip|semiconductor")
DATA_WEAK_RE = _W(r"data|ai|ml|analytics|statistic(s|al)?|science")
BUSINESS_RE = _W(r"business|sales|marketing|finance|financial|accounting|account|legal|recruit\w*|"
                 r"people|hr|engagement|program manager|program management|product manager|operations|"
                 r"strategy|strategist|communications|policy|partnerships?|customer|brand|content|design(er)?")
ENGINEER_RE = _W(r"engineer(ing)?|technician")


def categorize(title: str) -> str:
    """Strong technical words decide first; then MBA/business words; then the
    weak words ("data", "engineer") that are too generic to trust earlier."""
    if SOFTWARE_RE.search(title):
        return SOFTWARE
    if DATA_STRONG_RE.search(title):
        return DATA
    if HARDWARE_STRONG_RE.search(title):
        return HARDWARE
    if re.search(r"\bmba\b", title, re.I):
        return OTHER
    if DATA_WEAK_RE.search(title):
        return DATA
    if BUSINESS_RE.search(title):
        return OTHER
    if ENGINEER_RE.search(title):
        return HARDWARE
    return OTHER


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
    def category(self) -> str:
        return categorize(self.title)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category
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
