"""Range helpers (initial stub — not implemented)."""


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi) -> bool:
    return lo <= value <= hi
