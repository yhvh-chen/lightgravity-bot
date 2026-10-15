"""Report rendering (depends on geometry)."""
from .geometry import area, perimeter


def describe(shape):
    return (
        f"{shape['kind']}: area={area(shape):.2f} "
        f"perimeter={perimeter(shape):.2f}"
    )
