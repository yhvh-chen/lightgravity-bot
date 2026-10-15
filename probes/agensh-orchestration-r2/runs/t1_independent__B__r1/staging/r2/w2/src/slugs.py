"""Slug helpers."""

import re


def slugify(title: str) -> str:
    s = str(title).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
