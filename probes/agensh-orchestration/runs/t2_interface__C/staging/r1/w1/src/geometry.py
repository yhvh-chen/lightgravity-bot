"""Geometry helpers for supported shapes."""

import math


def area(shape):
    """Return the area of a shape dict."""
    kind = shape["kind"]
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unsupported shape kind: {kind!r}")


def perimeter(shape):
    """Return the perimeter/circumference of a shape dict."""
    kind = shape["kind"]
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unsupported shape kind: {kind!r}")
