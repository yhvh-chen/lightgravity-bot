"""Slug helpers."""

import re


def slugify(title: str) -> str:
    """Convert a title into a URL-friendly slug.

    Lowercases the input, replaces each run of non-alphanumeric
    characters with a single hyphen, and strips leading/trailing hyphens.
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
