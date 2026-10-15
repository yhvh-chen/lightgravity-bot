"""Range helpers."""


def clamp(value, lo, hi):
    """Clamp ``value`` into the inclusive range ``[lo, hi]``.

    Returns ``lo`` when ``value < lo``, ``hi`` when ``value > hi``,
    otherwise ``value`` unchanged.
    """
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    """Return True when ``lo <= value <= hi`` (bounds inclusive)."""
    return lo <= value <= hi
