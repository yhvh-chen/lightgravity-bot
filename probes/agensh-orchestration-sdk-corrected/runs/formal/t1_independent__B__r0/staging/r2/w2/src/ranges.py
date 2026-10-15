"""Range helpers."""


def clamp(value, lo, hi):
    """Return ``lo`` when ``value < lo``, ``hi`` when ``value > hi``, else ``value``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    """Return ``True`` iff ``lo <= value <= hi``."""
    return lo <= value <= hi
