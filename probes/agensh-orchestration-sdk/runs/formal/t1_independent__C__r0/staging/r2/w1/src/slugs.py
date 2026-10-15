"""Slug helpers."""

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert ``title`` into a lowercase, hyphen-separated slug.

    Lowercasing happens first so that uppercase letters are folded into their
    ASCII lowercase counterparts instead of being treated as separators.
    """
    return _NON_ALNUM.sub("-", title.lower()).strip("-")
