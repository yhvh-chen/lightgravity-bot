"""Slug helpers."""

import re


def slugify(title: str) -> str:
    """Convert a title into a URL-friendly slug.

    Lowercases the input, replaces each run of non-alphanumeric
    characters (anything outside a-z and 0-9) with a single "-",
    and strips leading/trailing "-".
    """
    lowered = title.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    return replaced.strip("-")
