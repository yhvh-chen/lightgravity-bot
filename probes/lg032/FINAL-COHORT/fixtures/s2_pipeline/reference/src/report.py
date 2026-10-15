"""Shape report (reference implementation)."""

from .shapes import area, perimeter


def describe(shape):
    return f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"
