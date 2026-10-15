"""Range helpers."""


def clamp(value, lo, hi):
    """Clamp *value* to the inclusive range ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    """Return ``True`` when ``lo <= value <= hi``."""
    return lo <= value <= hi
