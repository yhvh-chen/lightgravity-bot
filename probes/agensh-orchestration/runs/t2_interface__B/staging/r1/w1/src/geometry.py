"""Geometry helpers for the shared shape interface.

A shape is a dict with a ``kind`` key:

* ``{"kind": "rect", "width": <number>, "height": <number>}``
* ``{"kind": "circle", "radius": <number>}``

Unknown kinds raise :class:`ValueError`.
"""
import math


def area(shape):
    """Return the area of ``shape`` as a float."""
    kind = shape.get("kind")
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError("unknown shape kind: {!r}".format(kind))


def perimeter(shape):
    """Return the perimeter (circumference) of ``shape`` as a float."""
    kind = shape.get("kind")
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError("unknown shape kind: {!r}".format(kind))
