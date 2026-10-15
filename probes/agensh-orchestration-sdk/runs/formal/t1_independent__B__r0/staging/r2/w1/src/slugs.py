"""Slug helpers."""

import re

_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert a title into a URL-friendly slug.

    Lowercases the title, replaces every run of characters outside
    ``[a-z0-9]`` with a single ``'-'``, then strips leading/trailing ``'-'``.
    """
    return _NON_ALNUM_RUN.sub("-", title.lower()).strip("-")
