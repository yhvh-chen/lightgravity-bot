"""Label helpers (reference implementation)."""

import re


def slugify(title):
    text = str(title).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
