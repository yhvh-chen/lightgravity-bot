"""Range helpers."""


def clamp(value, lo, hi):
    """Return value bounded to the inclusive range [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    """Return True when lo <= value <= hi, else False."""
    return lo <= value <= hi
