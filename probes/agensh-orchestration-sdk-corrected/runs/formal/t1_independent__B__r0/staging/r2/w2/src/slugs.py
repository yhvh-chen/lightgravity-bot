"""Slug helpers."""

import re

_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Return an ASCII slug for ``title``.

    The title is lowercased, every maximal run of characters outside
    ``[a-z0-9]`` is collapsed into a single ``-``, and any leading or
    trailing ``-`` is removed.
    """
    lowered = title.lower()
    collapsed = _NON_ALNUM_RUN.sub("-", lowered)
    return collapsed.strip("-")
