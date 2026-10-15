"""Geometry helpers for shape area and perimeter."""
import math


def area(shape):
    kind = shape["kind"]
    if kind == "rect":
        return shape["width"] * shape["height"]
    if kind == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown shape kind: {shape.get('kind')!r}")


def perimeter(shape):
    kind = shape["kind"]
    if kind == "rect":
        return 2 * (shape["width"] + shape["height"])
    if kind == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown shape kind: {shape.get('kind')!r}")
