"""Slug helpers."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Lowercase ``title`` and collapse runs of non-alphanumerics to ``-``."""
    return _NON_ALNUM.sub("-", title.lower()).strip("-")
