"""Numeric helpers (reference implementation)."""


def clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def in_range(value, lo, hi):
    return lo <= value <= hi
