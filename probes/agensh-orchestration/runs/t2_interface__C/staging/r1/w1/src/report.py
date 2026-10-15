"""Report rendering helpers."""

from .geometry import area, perimeter


def describe(shape):
    """Return a formatted description of a shape."""
    return f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"
