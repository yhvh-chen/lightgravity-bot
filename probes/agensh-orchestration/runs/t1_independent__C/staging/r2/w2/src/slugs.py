"""Slug helpers."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert *title* into a URL-friendly slug.

    The title is lowercased, every run of characters outside ``a-z``/``0-9``
    is collapsed into a single ``"-"``, and leading/trailing dashes are
    stripped.
    """
    return _NON_ALNUM.sub("-", title.lower()).strip("-")
