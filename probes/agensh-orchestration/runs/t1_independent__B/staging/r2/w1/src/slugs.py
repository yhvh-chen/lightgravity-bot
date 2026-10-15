"""Slug helpers (initial stub — not implemented)."""

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    return _NON_ALNUM_RE.sub("-", title.lower()).strip("-")
