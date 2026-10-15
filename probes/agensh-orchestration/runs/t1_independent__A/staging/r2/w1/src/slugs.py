"""Slug helpers (initial stub — not implemented)."""

import re

_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    return _NON_ALNUM_RUN.sub("-", title.lower()).strip("-")
