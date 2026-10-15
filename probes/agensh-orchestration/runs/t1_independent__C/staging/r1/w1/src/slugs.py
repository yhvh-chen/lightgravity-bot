"""Slug helpers."""

import re


def slugify(title: str) -> str:
    """Return a URL-friendly slug for *title*.

    The title is lowercased, every run of non-alphanumeric characters is
    replaced with a single ``"-"``, and leading/trailing hyphens are removed.
    """
    lowered = title.lower()
    replaced = re.sub(r"[^a-z0-9]+", "-", lowered)
    return replaced.strip("-")
