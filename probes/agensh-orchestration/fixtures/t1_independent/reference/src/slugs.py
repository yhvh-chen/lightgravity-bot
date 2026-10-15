"""Reference solution for T1 (not visible to the model)."""
import re


def slugify(title: str) -> str:
    lowered = title.lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    return lo <= value <= hi
