"""Geometry helpers for plain dict shapes.

Frozen contract:
    rect   -> {"kind": "rect", "width": w, "height": h}
    circle -> {"kind": "circle", "radius": r}

Both ``area`` and ``perimeter`` raise ``ValueError`` for any unknown kind.
"""
import math


def area(shape):
    kind = shape["kind"]
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown shape kind: {kind!r}")


def perimeter(shape):
    kind = shape["kind"]
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown shape kind: {kind!r}")
