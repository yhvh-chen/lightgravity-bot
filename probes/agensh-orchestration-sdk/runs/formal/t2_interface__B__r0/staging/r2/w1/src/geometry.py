"""Geometry helpers for shape dicts.

A shape is represented as a plain ``dict`` whose ``"kind"`` key selects the
variant:

* ``{"kind": "rect", "width": ..., "height": ...}``
* ``{"kind": "circle", "radius": ...}``

Only the two kinds above are supported; anything else raises ``ValueError``.
"""
import math

# Canonical ``kind`` tags. Shared with report so that the two modules cannot
# drift apart on spelling.
KIND_RECT = "rect"
KIND_CIRCLE = "circle"


def area(shape):
    """Return the area of ``shape`` (``math.pi * r**2`` for circles)."""
    kind = shape["kind"]
    if kind == KIND_RECT:
        return shape["width"] * shape["height"]
    if kind == KIND_CIRCLE:
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown shape kind: {kind!r}")


def perimeter(shape):
    """Return the perimeter/circumference of ``shape``."""
    kind = shape["kind"]
    if kind == KIND_RECT:
        return 2 * (shape["width"] + shape["height"])
    if kind == KIND_CIRCLE:
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown shape kind: {kind!r}")
