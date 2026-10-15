"""Slug helpers."""

import re


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert *title* into a URL-friendly slug.

    Lowercases the input, collapses every run of non-alphanumeric
    characters (anything outside a-z and 0-9) into a single ``-``,
    and strips leading/trailing ``-`` from the result.
    """
    return _NON_ALNUM.sub("-", title.lower()).strip("-")
