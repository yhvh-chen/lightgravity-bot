"""Report rendering built on the geometry shape interface."""
from .geometry import area, perimeter


def describe(shape):
    """Return a one-line human readable description of ``shape``."""
    return (
        f"{shape['kind']}: area={area(shape):.2f} "
        f"perimeter={perimeter(shape):.2f}"
    )
