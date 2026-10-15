"""Slug helpers."""

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    lowered = title.lower()
    return _NON_ALNUM_RE.sub("-", lowered).strip("-")
