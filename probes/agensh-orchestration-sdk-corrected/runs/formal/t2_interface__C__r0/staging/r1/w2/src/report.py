"""Report rendering (depends on geometry)."""
from .geometry import area, perimeter


def describe(shape):
    """Return a formatted summary of *shape*.

    Delegates measurement to :mod:`geometry` so the reporting layer holds no
    geometry logic of its own; any unknown-kind error propagates from there.
    """
    return (
        f"{shape['kind']}: "
        f"area={area(shape):.2f} perimeter={perimeter(shape):.2f}"
    )
