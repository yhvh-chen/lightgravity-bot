"""Geometry helpers for shape dicts.

Shape interface (shared with ``report``):
- ``{"kind": "rect", "width": <num>, "height": <num>}``
- ``{"kind": "circle", "radius": <num>}``
"""
import math


def area(shape):
    """Return the area of ``shape``.

    Raises:
        ValueError: if ``shape["kind"]`` is not ``"rect"`` or ``"circle"``.
    """
    kind = shape["kind"]
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown shape kind: {kind!r}")


def perimeter(shape):
    """Return the perimeter (circumference) of ``shape``.

    Raises:
        ValueError: if ``shape["kind"]`` is not ``"rect"`` or ``"circle"``.
    """
    kind = shape["kind"]
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown shape kind: {kind!r}")
