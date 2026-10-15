"""Geometry helpers for the shared shape interface.

A shape is a dict:
  {"kind": "rect", "width": w, "height": h}
  {"kind": "circle", "radius": r}
"""
import math


def area(shape):
    """Return the area of ``shape``."""
    kind = shape["kind"]
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown shape kind: {kind!r}")


def perimeter(shape):
    """Return the perimeter (circumference) of ``shape``."""
    kind = shape["kind"]
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown shape kind: {kind!r}")
