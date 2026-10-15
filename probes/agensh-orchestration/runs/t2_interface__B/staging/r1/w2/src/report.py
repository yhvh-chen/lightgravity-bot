"""Report rendering (depends on geometry)."""
from . import geometry


def describe(shape):
    area = geometry.area(shape)
    perimeter = geometry.perimeter(shape)
    return f"{shape['kind']}: area={area:.2f} perimeter={perimeter:.2f}"
