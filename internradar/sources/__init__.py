"""Source adapters. Each module exposes NAME, fetch(cfg, client, today) and parse(...).
fetch() returns (internship postings, total jobs looked at)."""

from . import amazon, ashby, greenhouse, janestreet, lever, smartrecruiters, workday

SOURCES = {m.NAME: m for m in (greenhouse, lever, ashby, smartrecruiters, amazon, janestreet, workday)}
