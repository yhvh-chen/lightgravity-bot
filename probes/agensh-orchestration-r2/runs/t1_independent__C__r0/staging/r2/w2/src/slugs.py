"""Slug helpers."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert a title into a URL-friendly slug.

    Lowercases the input, replaces each run of non-alphanumeric
    characters (anything outside a-z, 0-9) with a single "-", and
    strips leading/trailing "-".
    """
    lowered = title.lower()
    return _NON_ALNUM.sub("-", lowered).strip("-")
